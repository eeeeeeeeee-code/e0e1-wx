# -*- coding: utf-8 -*-

import os
import shutil
import sys
import threading
import random
import string
from time import sleep

from .config import CONFIG, CONFIG_YAML
from .file_processor import LargeFileProcessor
from .wx_hook import WX_HOOK, run_wechat_hook
from .wxapkg_handler import WxapkgHandler
from .project_parser import ProjectParser


class Wx_tools:
    def __init__(self):
        wx_file = CONFIG().wx_file
        if wx_file == "":
            print(CONFIG_YAML.Colored().red("[!] 未配置wx文件夹"))
            exit(0)
        self.root_path = wx_file + "/Applet"
        self.root_path2 = wx_file + "\\Applet"
        self.hook_thread = None

    def remove_file_wx(self):
        """清理wx开头的文件夹"""
        try:
            with os.scandir(self.root_path) as entries:
                for entry in entries:
                    if entry.is_dir() and entry.name.startswith('wx') and len(entry.name) == 18:
                        shutil.rmtree(entry.path)
        except Exception as e:
            print(CONFIG_YAML.Colored().red(f"清理文件夹失败: {str(e)}"))

    def wx_file_wxapkg(self, path):
        """查找wxapkg文件所在目录"""
        current_path = path
        while True:
            entries = os.listdir(current_path)
            directories = [entry for entry in entries if os.path.isdir(os.path.join(current_path, entry))]
            if not directories:
                return current_path
            current_path = os.path.join(current_path, directories[0])

    def _get_window_text(self):
        """获取微信窗口信息"""
        try:
            wx_window_info = WX_HOOK().get_wechat_windows_info()
            window_text, pid, process_name = wx_window_info[0]
        except:
            window_text, pid, process_name = "HintWnd", "", ""
            
        if window_text == "HintWnd":
            print(CONFIG_YAML.Colored().blue("\n[+] 检测到HintWnd，代表没有抓到小程序名，为不影响程序，这里使用随机数"))
            window_text = window_text + "-" + ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(8))
            
        return window_text

    def _check_wxapkg_files(self, wxapkg_file, max_retries=2):
        """检查wxapkg文件是否存在，支持重试"""
        retry_count = 0
        wxapkg_found = False
        
        while retry_count <= max_retries and not wxapkg_found:
            sleep(5)
            # 检查目录中是否有文件
            files_count = sum([len(files) for _, _, files in os.walk(wxapkg_file)])
            
            # 检查是否存在wxapkg文件
            wxapkg_exists = False
            for root, _, files in os.walk(wxapkg_file):
                for file in files:
                    if file.endswith('.wxapkg'):
                        wxapkg_exists = True
                        break
                if wxapkg_exists:
                    break
            
            if files_count > 0 and wxapkg_exists:
                wxapkg_found = True
                # print(CONFIG_YAML.Colored().green("[+] 已找到wxapkg文件，继续处理..."))
            else:
                retry_count += 1
                if retry_count <= max_retries:
                    print(CONFIG_YAML.Colored().yellow(f"[!] 未找到wxapkg文件，第{retry_count}次重试..."))
                else:
                    print(CONFIG_YAML.Colored().yellow("[!] 重试次数已用完，将继续处理..."))
                    
        return wxapkg_found

    def _process_wxapkg(self, wxapkg_file, folder_file, args):
        """处理wxapkg文件"""
        pretty_enabled = args and args.pretty_tf
        restore_enabled = args and args.restore_project

        if args and args.devtools_hook:
            self.hook_thread = threading.Thread(target=run_wechat_hook, daemon=True)
            self.hook_thread.start()

        wxpg_tf = WxapkgHandler().process_directory(wxapkg_file, folder_file)

        if wxpg_tf:
            files = sum([len(files) for _, _, files in os.walk(wxapkg_file)])
            if files <= 1:
                print(CONFIG_YAML.Colored().red("[-] 没有生成对应的wxapkg加密文件,大概率为网络问题"))
            os.rmdir(folder_file)
            return False
            
        print(CONFIG_YAML.Colored().green("[+] 执行完毕-反编译源代码输出: {}".format(folder_file)))

        if restore_enabled:
            parser = ProjectParser()
            parser.parse_project(folder_file, pretty=pretty_enabled)

        LargeFileProcessor().path_process_directory(folder_file, folder_file, os.path.basename(folder_file))
        return True

    def monitor_new_wx(self, args=None):
        """监控新的微信小程序"""
        try:
            # 获取原始目录列表
            original_dirs = {entry.name for entry in os.scandir(self.root_path) if entry.is_dir()}
            sleep(0.3)
            # 获取新的目录列表
            new_dirs = {entry.name for entry in os.scandir(self.root_path) if entry.is_dir()}
            # 找出新增的文件夹
            new_folders = new_dirs - original_dirs

            for folder in new_folders:
                # 获取窗口标题
                window_text = self._get_window_text()
                folder_file = "./result/{}".format(window_text)
                wxapkg_file = self.wx_file_wxapkg(self.root_path2 + '\\' + folder)
                
                if os.path.isdir(folder_file):
                    print(CONFIG_YAML.Colored().magenta(f"\n[*]《{window_text}》文件已经存在"))
                else:
                    print(CONFIG_YAML.Colored().magenta("\n[*] 检测打开《{}》小程序,正在进行反编译中~~~".format(window_text)))
                    os.makedirs(folder_file, exist_ok=True)

                    # 检查wxapkg文件是否存在
                    self._check_wxapkg_files(wxapkg_file)
                    
                    # 处理wxapkg文件
                    if not self._process_wxapkg(wxapkg_file, folder_file, args):
                        break
                        
        except Exception as e:
            print(CONFIG_YAML.Colored().red(f"Wx_tools/monitor_new_wx bug: {e}"))
        except KeyboardInterrupt:
            print(CONFIG_YAML.Colored().yellow("[-] 程序被用户中断，正在退出..."))
            self._cleanup_resources()
            sys.exit(0)

    def _cleanup_resources(self):
        """清理资源"""
        if hasattr(self, 'hook_thread') and self.hook_thread and self.hook_thread.is_alive():
            pass

        for thread in threading.enumerate():
            if thread != threading.current_thread() and not thread.daemon:
                try:
                    thread._Thread__stop()
                except:
                    pass
