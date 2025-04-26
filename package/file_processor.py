# -*- coding: utf-8 -*-

import os
import mmap
import re
import threading
import filetype
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import CONFIG_YAML, CONFIG
from .output import Process_Print


class LargeFileProcessor:
    def __init__(self):
        config = CONFIG_YAML()
        self.pattern = re.compile(bytes(config.pattern_raw, 'utf-8'), re.VERBOSE)
        self._compiled_regex = {regex_name: re.compile(bytes(regex_pattern, "utf-8"), re.VERBOSE) for regex_name, regex_pattern in config._regex.items()}
        self.path_list = []
        self.reges_list = []
        self.existing_matches = set()
        self.lock = threading.Lock()

    def is_image(self, filepath):
        try:
            kind = filetype.guess(filepath)
            if kind is None:
                return True
            if kind.mime.startswith('image/'):
                return False
        except:
            return True

    def path_process_file(self, file_path):
        try:
            with open(file_path, 'r', encoding="gb18030") as file:
                with mmap.mmap(file.fileno(), length=0, access=mmap.ACCESS_READ) as mm:
                    unique_matches = {match[0].decode('utf-8') for match in self.pattern.findall(mm)}
                    new_matches = [match for match in unique_matches if match not in self.existing_matches and not any(img in match for img in [".jpg", ".png", ".jpeg", ".gif"])]
                    with self.lock:
                        self.path_list.extend([[file_path, match] for match in new_matches])
                        self.existing_matches.update(new_matches)
        except Exception as e:
            pass

    def reges_process_file(self, file_path):
        try:
            with open(file_path, 'r', encoding="gb18030") as file:
                with mmap.mmap(file.fileno(), length=0, access=mmap.ACCESS_READ) as mm:
                    for regex_name, regex_pattern in self._compiled_regex.items():
                        matches = {match for match in regex_pattern.findall(mm)}
                        unique_matches = set(matches)
                        with self.lock:
                            for match in unique_matches:
                                self.reges_list.append([regex_name, match, file_path])
        except Exception as e:
            pass

    def path_process_directory(self, directory_path, folder_file, title):
        print(CONFIG_YAML.Colored().magenta("[*] 开始搜索接口和泄露"))
        file_path = [
            os.path.join(root, file)
            for root, dirs, files in os.walk(directory_path)
            for file in files
        ]

        file_paths = [tar_path for tar_path in file_path if self.is_image(tar_path)]

        with ThreadPoolExecutor(max_workers=CONFIG_YAML().max_workers) as executor:
            future_to_file = {executor.submit(self.path_process_file, file_path): file_path for file_path in file_paths}
            for future in as_completed(future_to_file):
                future.result()

        with ThreadPoolExecutor(max_workers=CONFIG_YAML().max_workers) as executor:
            future_to_file = {executor.submit(self.reges_process_file, file_path): file_path for file_path in file_paths}
            for future in as_completed(future_to_file):
                future.result()

        def deduplicate0(key_results):
            sorted_results = sorted(key_results, key=lambda x: (x[0], x[1]))

            def unique(sequence):
                seen = set()
                return [item for item in sequence if (item[0], item[1]) not in seen and not seen.add((item[0], item[1]))]

            return unique(sorted_results)

        self.reges_list = deduplicate0(self.reges_list)

        xlsx_file = folder_file + "/" + CONFIG().proess_file
        try:
            Process_Print(xlsx_file).all_xlsx_file(self.path_list, ['文件位置', '泄露地址'], "接口")
        except:
            Process_Print(xlsx_file).all_xlsx_file([["", ""]], ['文件位置', '泄露地址'], "接口")

        try:
            Process_Print(xlsx_file).add_xlsx_file(self.reges_list, ['文件位置', '泄露key', '泄露内容'], "key")
        except:
            Process_Print(xlsx_file).add_xlsx_file([["", "", ""]], ['文件位置', '泄露key', '泄露内容'], "key")

        print(CONFIG_YAML.Colored().green("[+] 完毕！文件保存到{}".format(xlsx_file)))
