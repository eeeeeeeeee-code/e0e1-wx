"""实现微信相关 AES-CBC 与 PBKDF2 加解密算法。"""

from __future__ import annotations

import base64
import binascii
import hashlib

try:
    from Crypto.Cipher import AES
    from Crypto.Protocol.KDF import PBKDF2
except ImportError:
    AES = None
    PBKDF2 = None


AES_BLOCK_SIZE = 16


class CryptoError(ValueError):
    """加密解密输入或处理失败时抛出的业务异常。"""


def require_crypto_backend() -> None:
    """检查 PyCryptodome 后端是否可用。"""
    if AES is None or PBKDF2 is None:
        raise CryptoError("缺少依赖 pycryptodome，请先安装：pip install pycryptodome")


def pad(data: bytes, block_size: int = AES_BLOCK_SIZE) -> bytes:
    """对数据进行 PKCS7 填充，使其长度为 block_size 的整数倍。"""
    padding = block_size - len(data) % block_size
    return data + padding * bytes([padding])


def unpad(data: bytes) -> bytes:
    """移除 PKCS7 填充后的数据。"""
    return data[:-data[-1]]


def validate_base64(value: str, error_message: str) -> str | None:
    """校验 Base64 文本，失败时返回指定的中文错误提示。"""
    try:
        base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return error_message
    return None


def encrypt_data(data: str, iv_b64: str, key_b64: str) -> str:
    """加密数据，入参为明文、Base64 IV 和 Base64 SessionKey。"""
    if key_b64 == "":
        return "请输入密钥!"
    if iv_b64 == "":
        return "请输入初始向量!"
    if data == "":
        return "请输入原始数据!"

    base64_error = validate_base64(key_b64, "密钥不是有效的base64格式")
    if base64_error:
        return base64_error
    base64_error = validate_base64(iv_b64, "初始向量不是有效的base64格式")
    if base64_error:
        return base64_error

    try:
        require_crypto_backend()
        aes_iv = base64.b64decode(iv_b64)
        aes_key = base64.b64decode(key_b64)
        cipher = AES.new(aes_key, AES.MODE_CBC, aes_iv)
        encrypted = cipher.encrypt(pad(data.encode("utf-8"), AES_BLOCK_SIZE))
        return base64.b64encode(encrypted).decode("ascii")
    except Exception as exc:
        return str(exc)


def decrypt_data(data_b64: str, iv_b64: str, key_b64: str) -> str:
    """解密数据，入参为 Base64 密文、Base64 IV 和 Base64 SessionKey。"""
    if key_b64 == "":
        return "请输入密钥!"
    if iv_b64 == "":
        return "请输入初始向量!"
    if data_b64 == "":
        return "请输入加密数据!"

    base64_error = validate_base64(key_b64, "密钥不是有效的base64格式")
    if base64_error:
        return base64_error
    base64_error = validate_base64(iv_b64, "初始向量不是有效的base64格式")
    if base64_error:
        return base64_error

    try:
        require_crypto_backend()
        aes_iv = base64.b64decode(iv_b64)
        aes_cipher = base64.b64decode(data_b64)
        aes_key = base64.b64decode(key_b64)
        cipher = AES.new(aes_key, AES.MODE_CBC, aes_iv)
        decrypted = cipher.decrypt(aes_cipher)
        plaintext = unpad(decrypted)
        try:
            return plaintext.decode("utf-8")
        except UnicodeDecodeError:
            return "解码失败，十六进制结果: " + plaintext.hex()
    except Exception as exc:
        return str(exc)


def hmac_sha1(key: bytes, msg: bytes) -> bytes:
    """使用 SHA1 自实现 HMAC，供 PBKDF2 派生 AES Key 调用。"""
    block_size = 64
    if len(key) > block_size:
        key = hashlib.sha1(key).digest()

    key = key + b"\x00" * (block_size - len(key))
    o_key_pad = bytes(x ^ 0x5C for x in key)
    i_key_pad = bytes(x ^ 0x36 for x in key)
    return hashlib.sha1(o_key_pad + hashlib.sha1(i_key_pad + msg).digest()).digest()


def derive_key_bytes(wxid: str, salt: str) -> bytes:
    """根据 wxid 与 salt 派生 32 字节 AES Key。"""
    require_crypto_backend()
    wxid_text = str(wxid or "").strip()
    salt_text = str(salt or "").strip()
    if not wxid_text:
        raise CryptoError("wxid 不能为空。")
    if not salt_text:
        raise CryptoError("salt 不能为空。")
    return PBKDF2(
        wxid_text.encode("utf-8"),
        salt_text.encode("utf-8"),
        dkLen=32,
        count=1000,
        prf=lambda password, salt_value: hmac_sha1(password, salt_value),
    )


def generate_aes_key(wxid: str, salt: str, iv: str):
    """通过 PBKDF2 派生 AES Key，并创建 AES-CBC cipher。"""
    require_crypto_backend()
    dk = derive_key_bytes(wxid, salt)
    iv_bytes = str(iv or "").encode("utf-8")
    cipher = AES.new(dk, AES.MODE_CBC, iv_bytes)
    return dk, cipher


def derive_aes_key_result(wxid: str, salt: str, iv: str = "") -> dict:
    """派生 AES Key，并返回适合 UI 展示的 Base64 与 Hex 结果。"""
    dk = derive_key_bytes(wxid, salt)
    iv_text = str(iv or "")
    if iv_text:
        # 可选 IV 仅用于提前校验能否创建 AES-CBC cipher。
        generate_aes_key(wxid, salt, iv_text)
    return {
        "key_b64": base64.b64encode(dk).decode("ascii"),
        "key_hex": dk.hex(),
    }
