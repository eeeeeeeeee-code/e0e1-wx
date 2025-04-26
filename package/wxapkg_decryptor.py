# -*- coding: utf-8 -*-

from .crypto import generate_aes_key


class WxapkgDecryptor:
    """微信小程序wxapkg解密器"""

    def __init__(self):
        self.iv = "the iv: 16 bytes"
        self.salt = "saltiest"

    def decrypt_wxapkg(self, wxid, input_file, output_file=None):
        """解密wxapkg文件
        
        Args:
            wxid: 小程序ID
            input_file: 输入文件路径
            output_file: 输出文件路径，默认为input_file加上.dec后缀
            
        Returns:
            解密后的文件路径
        """
        if output_file is None:
            output_file = input_file + '.dec'

        try:
            with open(input_file, 'rb') as f:
                data_byte = f.read()

            _, cipher = generate_aes_key(wxid, self.salt, self.iv)

            origin_data = cipher.decrypt(data_byte[6:1024 + 6])

            af_data = bytearray(len(data_byte) - 1024 - 6)
            xor_key = 0x66
            if len(wxid) >= 2:
                xor_key = ord(wxid[len(wxid) - 2])

            for i, b in enumerate(data_byte[1024 + 6:]):
                af_data[i] = b ^ xor_key

            origin_data = origin_data[:1023] + af_data

            with open(output_file, 'wb') as f:
                f.write(origin_data)

            return output_file

        except Exception as e:
            print(f"解密失败: {str(e)}")
            return None
