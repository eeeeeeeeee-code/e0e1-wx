"""实现 wxapkg 解密、解包、路径安全和输出目录命名逻辑。"""

from __future__ import annotations

import hashlib
import os
import re
import struct
from pathlib import Path, PurePosixPath
from typing import Callable

try:
    from Crypto.Cipher import AES
except ImportError:
    try:
        from Cryptodome.Cipher import AES
    except ImportError:
        AES = None


MAGIC = b"V1MMWX"
SALT = b"saltiest"
IV = b"the iv: 16 bytes"
PBKDF2_ITER = 1000
KEY_LEN = 32
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class WxapkgError(ValueError):
    """wxapkg 解密或解包失败时抛出的业务异常。"""


class WxapkgCancelledError(WxapkgError):
    """Raised when wxapkg extraction is cancelled cooperatively."""


def require_crypto_backend() -> None:
    """检查 AES 解密依赖是否可用。"""
    if AES is None:
        raise WxapkgError("缺少依赖 pycryptodome，请先安装：pip install pycryptodome")


def safe_folder_name(value: str, fallback: str = "unknown") -> str:
    """把小程序名或 new_folder 名转换为安全的本地目录名。"""
    text = str(value or "").strip()
    text = INVALID_FILENAME_CHARS.sub("_", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or fallback


def safe_output_folder_name(value: str, fallback: str = "unknown") -> str:
    """生成稳定且尽量不碰撞的输出目录名。"""
    raw_text = str(value or "").strip()
    safe_text = safe_folder_name(raw_text, fallback)
    if not raw_text or safe_text == raw_text:
        return safe_text
    suffix = hashlib.sha1(raw_text.encode("utf-8", errors="ignore")).hexdigest()[:8]
    return f"{safe_text}_{suffix}"


def safe_output_folder_parts(value: str, fallback: str = "new_folder") -> list[str]:
    """Split a logical package path into safe local directory parts."""
    raw_text = str(value or "").strip().replace("\\", "/").lstrip("/")
    if not raw_text:
        return [fallback]

    posix_path = PurePosixPath(raw_text)
    parts: list[str] = []
    for part in posix_path.parts:
        if part in {"", ".", ".."}:
            return [fallback]
        parts.append(safe_folder_name(part, fallback))
    return parts or [fallback]


def safe_output_folder_path(output_root: Path, value: str, fallback: str = "new_folder") -> Path:
    """Build an output path without flattening nested wxid/subpackage folders."""
    return Path(output_root).joinpath(*safe_output_folder_parts(value, fallback))


def output_folder_display_name(output_root: Path, folder_dir: Path) -> str:
    """Return the relative output path shown in the file tree."""
    root = Path(output_root).expanduser().resolve(strict=False)
    folder = Path(folder_dir).expanduser().resolve(strict=False)
    try:
        return folder.relative_to(root).as_posix()
    except ValueError:
        return folder.name


def _derive_key(app_id: str) -> bytes:
    """使用 PBKDF2-SHA1 派生 wxapkg AES-256 密钥。"""
    return hashlib.pbkdf2_hmac("sha1", app_id.encode("utf-8"), SALT, PBKDF2_ITER, KEY_LEN)


def wxapkg_app_id(app_id: str) -> str:
    """从 new_folder 或逻辑路径中提取真实小程序 appid。"""
    raw_text = str(app_id or "").strip().replace("\\", "/").lstrip("/")
    if not raw_text:
        return ""
    parts = [part for part in PurePosixPath(raw_text).parts if part not in {"", ".", ".."}]
    return parts[0] if parts else raw_text


def decrypt_wxapkg(data: bytes, app_id: str) -> bytes:
    """解密单个 wxapkg 文件内容并返回解密后的字节数据。"""
    require_crypto_backend()
    if len(data) < 14:
        raise WxapkgError("文件太小，不是有效的 wxapkg")

    if data[:6] != MAGIC:
        # 未加密 wxapkg 通常直接以 0xBE 包头开始。
        if data[0:1] == b"\xbe":
            return data
        raise WxapkgError(f"未知 wxapkg 格式，magic={data[:6].hex()}")

    if len(data) < 1030:
        raise WxapkgError("加密 wxapkg 文件太小，无法解密头部")

    key = _derive_key(app_id)
    cipher = AES.new(key, AES.MODE_CBC, IV)
    decrypted_header = cipher.decrypt(data[6:1030])[:1023]

    xor_key = ord(app_id[-2]) if len(app_id) >= 2 else 0
    xor_decrypted = bytes(byte ^ xor_key for byte in data[1030:])
    return decrypted_header + xor_decrypted


def unpack_wxapkg(data: bytes) -> list[tuple[str, bytes]]:
    """解包 wxapkg 数据并返回内部文件路径与内容列表。"""
    if len(data) < 18:
        raise WxapkgError("数据太短，不是有效的 wxapkg")

    pos = 0
    marker1 = data[pos]
    if marker1 != 0xBE:
        raise WxapkgError(f"无效 wxapkg 包头：0x{marker1:02x}，期望 0xBE")
    pos += 1

    _info1 = struct.unpack(">I", data[pos : pos + 4])[0]
    pos += 4
    _index_info_length = struct.unpack(">I", data[pos : pos + 4])[0]
    pos += 4
    _body_info_length = struct.unpack(">I", data[pos : pos + 4])[0]
    pos += 4

    marker2 = data[pos]
    if marker2 != 0xED:
        raise WxapkgError(f"无效 wxapkg 索引标记：0x{marker2:02x}，期望 0xED")
    pos += 1

    file_count = struct.unpack(">I", data[pos : pos + 4])[0]
    pos += 4

    index_entries: list[tuple[str, int, int]] = []
    for _ in range(file_count):
        if pos + 4 > len(data):
            break
        name_len = struct.unpack(">I", data[pos : pos + 4])[0]
        pos += 4
        if name_len < 0 or pos + name_len > len(data):
            break
        name = data[pos : pos + name_len].decode("utf-8", errors="replace")
        pos += name_len
        if pos + 8 > len(data):
            break
        offset = struct.unpack(">I", data[pos : pos + 4])[0]
        pos += 4
        size = struct.unpack(">I", data[pos : pos + 4])[0]
        pos += 4
        index_entries.append((name, offset, size))

    files: list[tuple[str, bytes]] = []
    for name, offset, size in index_entries:
        if offset < 0 or size < 0:
            continue
        if offset + size <= len(data):
            files.append((name, data[offset : offset + size]))
    return files


def safe_output_path(output_dir: Path, inner_name: str) -> Path | None:
    """把 wxapkg 内部路径安全映射到输出目录，防止路径穿越。"""
    normalized = str(inner_name or "").lstrip("/").replace("\\", "/")
    posix_path = PurePosixPath(normalized)
    if not normalized or any(part in {"", ".", ".."} for part in posix_path.parts):
        return None

    output_root = output_dir.resolve()
    out_path = output_root.joinpath(*posix_path.parts)
    try:
        resolved = out_path.resolve(strict=False)
        os.path.commonpath([str(output_root), str(resolved)])
    except (OSError, ValueError):
        return None
    if os.path.commonpath([str(output_root), str(resolved)]) != str(output_root):
        return None
    return resolved


def extract_wxapkg(
    wxapkg_path: Path,
    output_dir: Path,
    app_id: str,
    cancel_callback: Callable[[], bool] | None = None,
) -> list[str]:
    """解密并解包 wxapkg 到指定目录，返回已写出的文件路径。"""
    raw = wxapkg_path.read_bytes()
    decrypted = decrypt_wxapkg(raw, app_id)
    files = unpack_wxapkg(decrypted)

    extracted: list[str] = []
    if cancel_callback is not None and cancel_callback():
        raise WxapkgCancelledError("wxapkg extraction cancelled")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files:
        if cancel_callback is not None and cancel_callback():
            raise WxapkgCancelledError("wxapkg extraction cancelled")
        out_path = safe_output_path(output_dir, name)
        if out_path is None:
            continue
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if cancel_callback is not None and cancel_callback():
            raise WxapkgCancelledError("wxapkg extraction cancelled")
        out_path.write_bytes(content)
        extracted.append(str(out_path))
    return extracted


def find_wxapkg_files(folder: Path) -> list[dict]:
    """递归扫描指定 new_folder 目录并返回所有 .wxapkg 文件信息。"""
    results: list[dict] = []
    if not folder.is_dir():
        return results
    for wxapkg_path in folder.rglob("*.wxapkg"):
        try:
            if not wxapkg_path.is_file():
                continue
            stat = wxapkg_path.stat()
        except OSError:
            continue
        results.append(
            {
                "path": str(wxapkg_path),
                "name": wxapkg_path.name,
                "size": stat.st_size,
            }
        )
    return sorted(results, key=lambda item: item["path"])


def package_output_dir(source_dir: Path, wxapkg_path: Path, folder_output_dir: Path) -> Path:
    """根据 wxapkg 相对路径生成互不覆盖的包输出目录。"""
    try:
        relative = wxapkg_path.relative_to(source_dir)
    except ValueError:
        relative = Path(wxapkg_path.name)
    relative_without_suffix = relative.with_suffix("")
    return safe_output_folder_path(folder_output_dir, relative_without_suffix.as_posix(), "package")


def normalize_new_folder_names(values: list[str] | tuple[str, ...] | None) -> list[str]:
    """规范化记录中的 new_folder 名称列表，并保持原始顺序去重。"""
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized


def path_inside_root(root: Path, child: Path) -> bool:
    """判断 child 路径是否位于 root 目录之内。"""
    try:
        root_resolved = root.resolve(strict=False)
        child_resolved = child.resolve(strict=False)
        return os.path.commonpath([str(root_resolved), str(child_resolved)]) == str(root_resolved)
    except (OSError, ValueError):
        return False


def decompile_wxapkg_file(
    source_dir: Path,
    folder_output_dir: Path,
    wxapkg_path: Path,
    app_id: str,
    progress_callback: Callable[[dict], None] | None = None,
    cancel_callback: Callable[[], bool] | None = None,
) -> dict:
    """反编译单个 wxapkg 文件并返回统计结果。"""
    output_dir = folder_output_dir
    extracted = extract_wxapkg(wxapkg_path, output_dir, wxapkg_app_id(app_id), cancel_callback=cancel_callback)
    result = {
        "wxapkg_path": str(wxapkg_path),
        "output_dir": str(output_dir),
        "file_count": len(extracted),
    }
    if progress_callback is not None:
        progress_callback(result)
    return result
