import base64
import binascii
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from .config import CONFIG_YAML


def pad(data, block_size):
    """对数据进行填充，使其长度为block_size的整数倍"""
    padding = block_size - len(data) % block_size
    return data + padding * bytes([padding])


def unpad(data):
    """移除填充的数据"""
    return data[:-data[-1]]


def encrypt_data(decrypted_data, iv, session_key):
    """加密数据"""
    if session_key == "":
        return "请输入密钥!"
    if iv == "":
        return "请输入初始向量!"
    if decrypted_data == "":
        return "请输入原始数据!"

    try:
        base64.b64decode(session_key)
    except binascii.Error:
        return "密钥不是有效的base64格式"
    try:
        base64.b64decode(iv)
    except binascii.Error:
        return "初始向量不是有效的base64格式"

    try:
        aes_iv = base64.b64decode(iv)
        aes_cipher = decrypted_data
        aes_key = base64.b64decode(session_key)

        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(aes_iv), backend=default_backend())
        encryptor = cipher.encryptor()
        aes_cipher = pad(aes_cipher.encode(), 16)
        result = encryptor.update(aes_cipher) + encryptor.finalize()

        return base64.b64encode(result).decode()
    except Exception as e:
        print(e)
        return str(e)


def decrypt_data(encrypted_data, iv, session_key):
    """解密数据"""
    if session_key == "":
        return "请输入密钥!"
    if iv == "":
        return "请输入初始向量!"
    if encrypted_data == "":
        return "请输入加密数据!"

    try:
        base64.b64decode(session_key)
    except binascii.Error:
        return "密钥不是有效的base64格式"
    try:
        base64.b64decode(iv)
    except binascii.Error:
        return "初始向量不是有效的base64格式"

    try:
        aes_iv = base64.b64decode(iv)
        aes_cipher = base64.b64decode(encrypted_data)
        aes_key = base64.b64decode(session_key)

        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(aes_iv), backend=default_backend())
        decryptor = cipher.decryptor()
        result = decryptor.update(aes_cipher) + decryptor.finalize()

        try:
            return unpad(result).decode('utf-8')
        except UnicodeDecodeError:
            # 如果UTF-8解码失败，返回十六进制表示
            return "解码失败，十六进制结果: " + unpad(result).hex()
    except Exception as e:
        print(e)
        return str(e)


class CryptTools:
    """加解密工具类"""
    def __init__(self):
        self.color = CONFIG_YAML.Colored()

    def run_encrypt_mode(self):
        """运行加密模式"""
        print(self.color.magenta("=== 加密模式 ==="))
        session_key = input(self.color.cran("请输入SessionKey (base64格式): "))
        iv = input(self.color.cran("请输入初始向量IV (base64格式): "))
        decrypted_data = input(self.color.cran("请输入待加密内容: "))
        result = encrypt_data(decrypted_data, iv, session_key)
        print(self.color.green("\n加密结果: "+result))

    def run_decrypt_mode(self):
        """运行解密模式"""
        print(self.color.magenta("=== 解密模式 ==="))
        session_key = input(self.color.cran("请输入SessionKey (base64格式): "))
        iv = input(self.color.cran("请输入初始向量IV (base64格式): "))
        encrypted_data = input(self.color.cran("请输入待解密内容 (base64格式): "))
        result = decrypt_data(encrypted_data, iv, session_key)
        print(self.color.green("\n解密结果: "+result))
