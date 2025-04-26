# -*- coding: utf-8 -*-

import os
import json
import re
from .config import CONFIG_YAML


class ConfigParser:
    """配置文件解析器"""

    def __init__(self):
        pass

    def parse_config(self, source_dir):
        """解析配置文件
        
        Args:
            source_dir: 源目录
            
        Returns:
            bool: 是否成功
        """
        try:
            print(CONFIG_YAML.Colored().magenta("[*] 开始解析配置文件..."))

            app_config_path = os.path.join(source_dir, 'app-config.json')
            if not os.path.exists(app_config_path):
                print(CONFIG_YAML.Colored().yellow("未找到app-config.json文件，跳过配置解析"))
                return False

            with open(app_config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            pages = config_data.get('pages', [])
            entry_page_path = config_data.get('entryPagePath', '')

            if entry_page_path and pages:

                entry_page = self._change_ext(entry_page_path, '')
                if entry_page in pages:
                    pages.remove(entry_page)
                    pages.insert(0, entry_page)

            app_json = {
                'pages': pages,
                'window': config_data.get('global', {}).get('window', {}),
                'tabBar': config_data.get('tabBar', {}),
                'networkTimeout': config_data.get('networkTimeout', {})
            }

            if 'subPackages' in config_data:
                subpackages = []
                for subpackage in config_data['subPackages']:
                    root = subpackage.get('root', '')
                    if not root:
                        continue

                    if not root.endswith('/'):
                        root += '/'

                    root = root.lstrip('/')

                    sub_pages = []
                    for i in range(len(app_json['pages']) - 1, -1, -1):
                        page = app_json['pages'][i]
                        if page.startswith(root):

                            app_json['pages'].pop(i)

                            sub_page = page[len(root):]
                            if sub_page not in sub_pages:
                                sub_pages.append(sub_page)

                    subpackages.append({
                        'root': root,
                        'pages': sub_pages
                    })

                app_json['subPackages'] = subpackages

            if 'navigateToMiniProgramAppIdList' in config_data:
                app_json['navigateToMiniProgramAppIdList'] = config_data['navigateToMiniProgramAppIdList']

            if 'workers' in config_data:
                app_json['workers'] = config_data['workers']

            if 'debug' in config_data:
                app_json['debug'] = config_data['debug']

            app_json_path = os.path.join(source_dir, 'app.json')
            with open(app_json_path, 'w', encoding='utf-8') as f:
                json.dump(app_json, f, ensure_ascii=False, indent=4)

            if 'page' in config_data:
                for page_path, page_config in config_data['page'].items():

                    if page_path == 'app.json':
                        continue

                    json_path = self._change_ext(page_path, '.json')
                    full_json_path = os.path.join(source_dir, json_path)

                    os.makedirs(os.path.dirname(full_json_path), exist_ok=True)

                    with open(full_json_path, 'w', encoding='utf-8') as f:
                        json.dump(page_config.get('window', {}), f, ensure_ascii=False, indent=4)

            if 'extAppid' in config_data:
                ext_json = {
                    'extEnable': True,
                    'extAppid': config_data['extAppid'],
                    'ext': config_data.get('ext', {})
                }

                ext_json_path = os.path.join(source_dir, 'ext.json')
                with open(ext_json_path, 'w', encoding='utf-8') as f:
                    json.dump(ext_json, f, ensure_ascii=False, indent=4)

            self._process_app_service(source_dir, config_data)

            return True

        except Exception as e:
            print(CONFIG_YAML.Colored().red(f"解析配置文件失败: {str(e)}"))
            return False

    def _process_app_service(self, source_dir, config_data):
        """处理app-service.js中的配置"""
        app_service_path = os.path.join(source_dir, 'app-service.js')
        if not os.path.exists(app_service_path):
            return

        try:
            with open(app_service_path, 'r', encoding='utf-8', errors='ignore') as f:
                service_content = f.read()

            pattern = r'__wxAppCode__\[\'([^\']+\.json)\'\]\s*=\s*({[^;]*});'
            matches = re.findall(pattern, service_content)

            for match in matches:
                name = match[0]
                json_str = match[1]

                name = self._sanitize_path(name)

                try:

                    json_data = json.loads(json_str)

                    json_path = self._change_ext(name, '.json')
                    full_json_path = os.path.join(source_dir, json_path)

                    try:
                        os.makedirs(os.path.dirname(full_json_path), exist_ok=True)
                    except OSError as e:
                        print(CONFIG_YAML.Colored().yellow(f"创建目录失败: {str(e)}"))
                        continue

                    with open(full_json_path, 'w', encoding='utf-8') as f:
                        json.dump(json_data, f, ensure_ascii=False, indent=4)

                except json.JSONDecodeError:
                    print(CONFIG_YAML.Colored().yellow(f"无法解析JSON: {name}"))
                except OSError as e:
                    print(CONFIG_YAML.Colored().yellow(f"写入文件失败: {str(e)}"))

            if 'subPackages' in config_data:
                for subpackage in config_data['subPackages']:
                    root = subpackage.get('root', '')
                    if not root:
                        continue

                    if not root.endswith('/'):
                        root += '/'

                    root = root.lstrip('/')

                    sub_service_path = os.path.join(source_dir, root, 'app-service.js')
                    if not os.path.exists(sub_service_path):
                        continue

                    with open(sub_service_path, 'r', encoding='utf-8', errors='ignore') as f:
                        sub_service_content = f.read()

                    matches = re.findall(pattern, sub_service_content)

                    for match in matches:
                        name = match[0]
                        json_str = match[1]

                        name = self._sanitize_path(name)

                        try:

                            json_data = json.loads(json_str)

                            json_path = self._change_ext(name, '.json')
                            full_json_path = os.path.join(source_dir, json_path)

                            try:
                                os.makedirs(os.path.dirname(full_json_path), exist_ok=True)
                            except OSError as e:
                                print(CONFIG_YAML.Colored().yellow(f"创建子包目录失败: {str(e)}"))
                                continue

                            with open(full_json_path, 'w', encoding='utf-8') as f:
                                json.dump(json_data, f, ensure_ascii=False, indent=4)
                                
                        except json.JSONDecodeError:
                            print(CONFIG_YAML.Colored().yellow(f"无法解析JSON: {name}"))
                        except OSError as e:
                            print(CONFIG_YAML.Colored().yellow(f"写入子包文件失败: {str(e)}"))

        except Exception as e:
            print(CONFIG_YAML.Colored().yellow(f"处理app-service.js时出错: {str(e)}"))

    def _sanitize_path(self, path):
        """清理路径中的非法字符"""

        invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        for char in invalid_chars:
            path = path.replace(char, '_')

        if path.endswith(':'):
            path = path[:-1] + '_'

        return path

    def _change_ext(self, filename, new_ext):
        """更改文件扩展名"""
        ext = os.path.splitext(filename)[1]
        return filename[:-len(ext)] + new_ext if ext else filename + new_ext
