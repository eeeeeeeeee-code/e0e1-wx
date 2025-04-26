# -*- coding: utf-8 -*-
import os
import struct
from .file_utils import ensure_dir_exists
from .config import CONFIG_YAML


class WxapkgFile(object):
    """wxapkg文件中的单个文件信息"""
    def __init__(self):
        self.nameLen = 0
        self.name = ""
        self.offset = 0
        self.size = 0

class WxapkgUnpacker:
    """微信小程序wxapkg解包器"""

    def unpack_wxapkg(self, wxapkg_file, output_dir=None, overwrite=True):
        """解包wxapkg文件

        Args:
            wxapkg_file: wxapkg文件路径
            output_dir: 输出目录，默认为wxapkg文件名加_dir
            overwrite: 是否覆盖已存在的文件，默认为True
            pretty: 是否美化代码，默认为False

        Returns:
            解包后的目录路径
        """
        try:
            if output_dir is None:
                output_dir = wxapkg_file + '_dir'

            ensure_dir_exists(output_dir)

            with open(wxapkg_file, "rb") as f:

                first_mark = struct.unpack('B', f.read(1))[0]
                info1 = struct.unpack('>L', f.read(4))[0]
                index_info_length = struct.unpack('>L', f.read(4))[0]
                body_info_length = struct.unpack('>L', f.read(4))[0]
                last_mark = struct.unpack('B', f.read(1))[0]

                if first_mark != 0xBE or last_mark != 0xED:
                    print('不是有效的wxapkg文件!')
                    return None

                file_count = struct.unpack('>L', f.read(4))[0]

                file_list = []
                for i in range(file_count):
                    data = WxapkgFile()
                    data.nameLen = struct.unpack('>L', f.read(4))[0]
                    data.name = f.read(data.nameLen)
                    data.offset = struct.unpack('>L', f.read(4))[0]
                    data.size = struct.unpack('>L', f.read(4))[0]
                    file_list.append(data)

                success_count = 0
                skip_count = 0
                error_count = 0

                for i, d in enumerate(file_list):

                    try:

                        file_name = d.name.decode("utf-8")

                        while file_name.startswith('/') or file_name.startswith('\\'):
                            file_name = file_name[1:]

                        full_path = os.path.join(output_dir, file_name)

                        full_path = os.path.normpath(full_path)

                        if not os.path.abspath(full_path).startswith(os.path.abspath(output_dir)):
                            print(f"警告: 文件路径 {full_path} 不在输出目录内，已跳过")
                            skip_count += 1
                            continue

                        dir_path = os.path.dirname(full_path)

                        ensure_dir_exists(dir_path)

                        if os.path.exists(full_path):
                            if not overwrite:
                                skip_count += 1
                                continue

                        with open(full_path, 'wb') as w:
                            f.seek(d.offset)
                            w.write(f.read(d.size))
                            success_count += 1
                    except Exception as e:
                        print(f"处理文件时出错: {str(e)}")
                        error_count += 1

                print(CONFIG_YAML.Colored().blue(f"[+] 解包完成: 成功 {success_count} 个文件, 跳过 {skip_count} 个文件, 失败 {error_count} 个文件"))

            return output_dir

        except Exception as e:
            print(CONFIG_YAML.Colored().red(f"解包失败: {str(e)}"))
            return None
