# -*- coding: utf-8 -*-


import os
import tempfile
from .wxapkg_decryptor import WxapkgDecryptor
from .wxapkg_unpacker import WxapkgUnpacker
from .file_utils import find_wxapkg_files, extract_wxid_from_path, ensure_dir_exists, sort_wxapkg_files
from .config import CONFIG_YAML
from .project_restorer import ProjectRestorer


class WxapkgHandler:
    """微信小程序wxapkg处理器"""

    def __init__(self):
        self.decryptor = WxapkgDecryptor()
        self.unpacker = WxapkgUnpacker()
        self.restorer = ProjectRestorer()

    def process_directory(self, input_dir, output_dir, pretty=False, restore_structure=False):
        """处理目录下的所有wxapkg文件

        Args:
            input_dir: 要处理的目录
            output_dir: 输出目录
            pretty: 是否美化代码，默认为False
            restore_structure: 是否恢复项目结构，默认为False

        Returns:
            布尔值，表示处理是否成功（至少有一个文件成功处理）
        """
        success_count = 0
        failed_count = 0

        wxid = extract_wxid_from_path(input_dir)
        if not wxid:
            print(f"无法从路径中提取wxid: {input_dir}")
            return False

        wxapkg_files = find_wxapkg_files(input_dir)
        if not wxapkg_files:
            print(f"在目录中未找到wxapkg文件: {input_dir}")
            return False

        wxapkg_files = sort_wxapkg_files(wxapkg_files)

        ensure_dir_exists(output_dir)

        for wxapkg_file in wxapkg_files:
            try:

                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    temp_path = temp_file.name

                decrypted_file = self.decryptor.decrypt_wxapkg(wxid, wxapkg_file, temp_path)
                if not decrypted_file:
                    failed_count += 1

                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    continue

                unpacked_dir = self.unpacker.unpack_wxapkg(decrypted_file, output_dir)

                if os.path.exists(temp_path):
                    os.unlink(temp_path)

                if not unpacked_dir:
                    failed_count += 1
                    continue

                success_count += 1

            except Exception as e:
                print(f"处理文件时出错: {wxapkg_file}, 错误: {str(e)}")
                failed_count += 1

        if restore_structure and success_count > 0:
            try:
                print(CONFIG_YAML.Colored().green(f"所有包解包完成，开始恢复项目结构..."))

                app_config_path = os.path.join(output_dir, 'app-config.json')
                if os.path.exists(app_config_path):
                    self.restorer.restore_project_structure(output_dir)
                else:
                    print(CONFIG_YAML.Colored().yellow(f"未找到app-config.json文件，跳过项目结构恢复"))
            except Exception as e:
                print(CONFIG_YAML.Colored().red(f"恢复项目结构过程中出错: {str(e)}"))

        if pretty and success_count > 0:
            try:
                from .formatter import Formatter
                print(CONFIG_YAML.Colored().green(f"所有包解包完成，开始统一格式化代码..."))
                formatter = Formatter()
                formatter.format_directory(output_dir)
            except ImportError:
                print(CONFIG_YAML.Colored().red("警告: 格式化器模块未找到，跳过代码美化"))
            except Exception as e:
                print(CONFIG_YAML.Colored().red(f"代码格式化过程中出错: {str(e)}"))

        return success_count == 0
