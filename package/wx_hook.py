# -*- coding: utf-8 -*-

import sys
import frida
import psutil
import win32gui
import win32process

from .config import CONFIG_YAML


class WX_HOOK:
    def __init__(self, js_path=r"./tools/WeChatAppEx.exe.js"):
        self.hook_js_path = js_path
        self.session = None

    def get_wechat_windows_info(self):
        try:
            window_info = []

            def callback(hwnd, extra):
                window_text = win32gui.GetWindowText(hwnd)
                if window_text:
                    pid = win32process.GetWindowThreadProcessId(hwnd)
                    process = psutil.Process(pid[1])
                    if process.name() == "WeChatAppEx.exe" and window_text not in ["微信", "MSCTFIME UI", "Default IME"]:
                        window_info.append((window_text, pid[1], process.name()))

            win32gui.EnumWindows(callback, None)

            return window_info
        except Exception as e:
            print(CONFIG_YAML.Colored().red("WX_HOOK/get_wechat_windows_info bug: {}".format(e)))

    def hook_wechat(self, on_message):
        window_info = self.get_wechat_windows_info()
        if window_info:
            window_text, pid, process_name = window_info[0]
            print(CONFIG_YAML.Colored().cran("[+] Window Title: {}, PID: {}, Process Name: {}".format(window_text, pid, process_name)))
            try:
                self.session = frida.attach(pid)
                with open(self.hook_js_path, 'r', encoding='utf8') as f:
                    script = self.session.create_script(f.read())

                script.on('message', on_message)
                script.load()
                sys.stdin.read()
            except KeyboardInterrupt:
                print(CONFIG_YAML.Colored().red('Detaching from process...'))
            finally:
                if self.session is not None:
                    self.session.detach()
        else:
            print(CONFIG_YAML.Colored().red("检测小程序没有打开"))


def on_message(message, data):
    if message['type'] == 'send':
        print(CONFIG_YAML.Colored().cran("[*] {0}".format(message['payload'])))
    else:
        print(CONFIG_YAML.Colored().cran(str(message)))


def run_wechat_hook():
    try:
        hook = WX_HOOK()
        hook.hook_wechat(on_message)
    except KeyboardInterrupt:
        print(CONFIG_YAML.Colored().yellow("Hook线程被中断，正在退出..."))
    except Exception as e:
        print(CONFIG_YAML.Colored().red(f"Hook线程出错: {e}"))
    finally:
        if 'hook' in locals() and hook.session is not None:
            try:
                hook.session.detach()
            except:
                pass
