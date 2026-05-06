"""在 Windows 上识别微信小程序窗口、进程和启动时间。"""

import ctypes
import ctypes.wintypes
import sys
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

INVALID_WINDOW_TITLES = {"微信", "HintWnd", "Sogou_TSF_UI", "MSCTFIME UI", "Default IME"}


def process_details(pid: int) -> dict:
    """根据进程 ID 获取进程名与启动时间。"""
    if pid <= 0:
        return {"process": "", "start_time": 0.0}
    if psutil is not None:
        try:
            process = psutil.Process(pid)
            return {"process": process.name(), "start_time": float(process.create_time())}
        except (psutil.Error, OSError):
            return {"process": "", "start_time": 0.0}
    if sys.platform != "win32":
        return {"process": "", "start_time": 0.0}

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
    kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.wintypes.HANDLE,
        ctypes.wintypes.DWORD,
        ctypes.wintypes.LPWSTR,
        ctypes.POINTER(ctypes.wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = ctypes.wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = [
        ctypes.wintypes.HANDLE,
        ctypes.POINTER(ctypes.wintypes.FILETIME),
        ctypes.POINTER(ctypes.wintypes.FILETIME),
        ctypes.POINTER(ctypes.wintypes.FILETIME),
        ctypes.POINTER(ctypes.wintypes.FILETIME),
    ]
    kernel32.GetProcessTimes.restype = ctypes.wintypes.BOOL
    kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
    process_query_limited = 0x1000
    handle = kernel32.OpenProcess(process_query_limited, False, pid)
    if not handle:
        return {"process": "", "start_time": 0.0}
    try:
        image_buffer = ctypes.create_unicode_buffer(1024)
        image_size = ctypes.wintypes.DWORD(len(image_buffer))
        process_name = ""
        if kernel32.QueryFullProcessImageNameW(handle, 0, image_buffer, ctypes.byref(image_size)):
            process_name = Path(image_buffer.value).name

        creation = ctypes.wintypes.FILETIME()
        exit_time = ctypes.wintypes.FILETIME()
        kernel = ctypes.wintypes.FILETIME()
        user = ctypes.wintypes.FILETIME()
        start_time = 0.0
        if kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            filetime = (creation.dwHighDateTime << 32) + creation.dwLowDateTime
            start_time = filetime / 10_000_000 - 11_644_473_600
        return {"process": process_name, "start_time": start_time}
    finally:
        kernel32.CloseHandle(handle)


def pid_is_running(pid: int) -> bool:
    """判断指定进程 ID 是否仍在运行。"""
    if pid <= 0:
        return False
    if psutil is not None:
        try:
            process = psutil.Process(pid)
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except (psutil.Error, OSError):
            return False
    if sys.platform != "win32":
        return False

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
    kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [ctypes.wintypes.HANDLE, ctypes.POINTER(ctypes.wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = ctypes.wintypes.BOOL
    kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
    process_query_limited = 0x1000
    still_active = 259
    handle = kernel32.OpenProcess(process_query_limited, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def list_wechat_app_windows() -> list[dict]:
    """枚举当前可见的 WeChatAppEx.exe 小程序窗口。"""
    if sys.platform != "win32":
        return []

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    enum_windows_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    user32.EnumWindows.argtypes = [enum_windows_proc, ctypes.wintypes.LPARAM]
    user32.EnumWindows.restype = ctypes.wintypes.BOOL
    user32.IsWindowVisible.argtypes = [ctypes.wintypes.HWND]
    user32.IsWindowVisible.restype = ctypes.wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [ctypes.wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD
    windows: list[dict] = []

    @enum_windows_proc
    def enum_window(hwnd, _lparam):
        """枚举单个窗口并筛选微信小程序进程。"""
        if not user32.IsWindowVisible(hwnd):
            return True

        title_length = user32.GetWindowTextLengthW(hwnd)
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        if title_length:
            user32.GetWindowTextW(hwnd, title_buffer, title_length + 1)
        window_title = title_buffer.value.strip()

        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        details = process_details(int(pid.value))
        if details["process"].lower() != "wechatappex.exe":
            return True
        if window_title in INVALID_WINDOW_TITLES:
            return True

        windows.append(
            {
                "title": window_title,
                "pid": int(pid.value),
                "process": details["process"],
                "start_time": float(details["start_time"] or 0.0),
                "hwnd": int(hwnd),
            }
        )
        return True

    user32.EnumWindows(enum_window, 0)
    windows.sort(key=lambda item: (item.get("start_time") or 0.0, item.get("pid") or 0))
    return windows
