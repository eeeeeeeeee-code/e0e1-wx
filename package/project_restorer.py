# -*- coding: utf-8 -*-

import hashlib
import json
import os

from .config import CONFIG_YAML


class ProjectRestorer:
    """微信小程序项目结构还原器"""

    _instance = None

    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = ProjectRestorer()
        return cls._instance

    def __init__(self):
        """初始化还原器"""
        self.colored = CONFIG_YAML.Colored()

    def restore_project_structure(self, source_dir):
        """还原项目结构
        
        Args:
            source_dir: 解包后的源目录
        
        Returns:
            bool: 是否成功
        """
        try:

            app_config_path = os.path.join(source_dir, 'app-config.json')
            if not os.path.exists(app_config_path):
                print(CONFIG_YAML.Colored().red("未找到app-config.json文件，无法还原项目结构"))
                return False

            with open(app_config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            self._create_app_json(source_dir, config_data)

            self._process_pages(source_dir, config_data)

            self._process_subpackages(source_dir, config_data)

            self._process_tabbar(source_dir, config_data)

            self._process_ext_json(source_dir, config_data)

            self._clean_component_configs(source_dir)

            print(CONFIG_YAML.Colored().green("[+] 项目结构还原完成"))
            return True

        except Exception as e:
            print(CONFIG_YAML.Colored().red(f"还原项目结构失败: {str(e)}"))
            return False

    def _create_app_json(self, source_dir, config_data):
        """创建app.json文件"""
        app_json = {
            "pages": [],
            "window": {},
            "tabBar": {},
            "networkTimeout": {},
            "debug": False
        }

        mapping = {
            "pages": "pages",
            "global.window": "window",
            "tabBar": "tabBar",
            "networkTimeout": "networkTimeout",
            "subPackages": "subPackages",
            "navigateToMiniProgramAppIdList": "navigateToMiniProgramAppIdList",
            "workers": "workers",
            "debug": "debug"
        }

        for config_key, app_key in mapping.items():
            if "." in config_key:

                parts = config_key.split(".")
                if parts[0] in config_data and parts[1] in config_data[parts[0]]:
                    app_json[app_key] = config_data[parts[0]][parts[1]]
            elif config_key in config_data:
                app_json[app_key] = config_data[config_key]

        app_json_path = os.path.join(source_dir, 'app.json')
        with open(app_json_path, 'w', encoding='utf-8') as f:
            json.dump(app_json, f, ensure_ascii=False, indent=4)

    def _process_pages(self, source_dir, config_data):
        """处理页面文件"""
        if "page" not in config_data:
            return

        for page_path, page_config in config_data["page"].items():

            if page_path == "app.json":
                continue

            json_path = self._change_ext(page_path, ".json")
            full_json_path = os.path.join(source_dir, json_path)

            os.makedirs(os.path.dirname(full_json_path), exist_ok=True)

            with open(full_json_path, 'w', encoding='utf-8') as f:
                json.dump(page_config.get("window", {}), f, ensure_ascii=False, indent=4)

    def _process_subpackages(self, source_dir, config_data):
        """处理子包"""
        if "subPackages" not in config_data:
            return

        for subpackage in config_data["subPackages"]:
            root = subpackage.get("root", "")
            pages = subpackage.get("pages", [])

            if not root or not pages:
                continue

            if not root.endswith('/'):
                root += '/'

            root = root.lstrip('/')

            for page in pages:
                page_path = os.path.join(root, page)
                self._create_page_files(source_dir, page_path)

    def _create_page_files(self, source_dir, page_path):
        """创建页面相关文件"""

        js_path = self._change_ext(page_path, ".js")
        full_js_path = os.path.join(source_dir, js_path)
        os.makedirs(os.path.dirname(full_js_path), exist_ok=True)
        with open(full_js_path, 'w', encoding='utf-8') as f:
            f.write(f"// {js_path}\nPage({{data: {{}}}});")

        wxml_path = self._change_ext(page_path, ".wxml")
        full_wxml_path = os.path.join(source_dir, wxml_path)
        os.makedirs(os.path.dirname(full_wxml_path), exist_ok=True)
        with open(full_wxml_path, 'w', encoding='utf-8') as f:
            f.write(f"<!--{wxml_path}--><text>{wxml_path}</text>")

        wxss_path = self._change_ext(page_path, ".wxss")
        full_wxss_path = os.path.join(source_dir, wxss_path)
        os.makedirs(os.path.dirname(full_wxss_path), exist_ok=True)
        with open(full_wxss_path, 'w', encoding='utf-8') as f:
            f.write(f"/* {wxss_path} */")

    def _process_tabbar(self, source_dir, config_data):
        """处理TabBar图标"""
        if "tabBar" not in config_data or "list" not in config_data["tabBar"]:
            return

        file_digests = self._scan_files_for_digests(source_dir)

        for item in config_data["tabBar"]["list"]:
            if "pagePath" in item:
                item["pagePath"] = self._change_ext(item["pagePath"], "")

            if "iconData" in item:
                icon_hash = hashlib.md5(item["iconData"].encode()).hexdigest()
                if icon_hash in file_digests:
                    item["iconPath"] = self._fix_dir(file_digests[icon_hash], source_dir)
                    del item["iconData"]

            if "selectedIconData" in item:
                icon_hash = hashlib.md5(item["selectedIconData"].encode()).hexdigest()
                if icon_hash in file_digests:
                    item["selectedIconPath"] = self._fix_dir(file_digests[icon_hash], source_dir)
                    del item["selectedIconData"]

        self._update_app_json(source_dir, {"tabBar": config_data["tabBar"]})

    def _scan_files_for_digests(self, directory):
        """扫描目录中的所有文件并计算摘要"""
        file_digests = {}
        for root, _, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'rb') as f:
                        content = f.read()
                        file_hash = hashlib.md5(content).hexdigest()
                        file_digests[file_hash] = file_path
                except Exception:
                    pass
        return file_digests

    def _update_app_json(self, source_dir, updates):
        """更新app.json文件"""
        app_json_path = os.path.join(source_dir, 'app.json')
        if os.path.exists(app_json_path):
            with open(app_json_path, 'r', encoding='utf-8') as f:
                app_json = json.load(f)

            for key, value in updates.items():
                app_json[key] = value

            with open(app_json_path, 'w', encoding='utf-8') as f:
                json.dump(app_json, f, ensure_ascii=False, indent=4)

    def _process_ext_json(self, source_dir, config_data):
        """处理ext.json"""
        if "extAppid" not in config_data:
            return

        ext_json = {
            "extEnable": True,
            "extAppid": config_data["extAppid"],
            "ext": config_data.get("ext", {})
        }

        ext_json_path = os.path.join(source_dir, 'ext.json')
        with open(ext_json_path, 'w', encoding='utf-8') as f:
            json.dump(ext_json, f, ensure_ascii=False, indent=4)

        print(self.colored.blue("已创建ext.json文件"))

    def _change_ext(self, filename, new_ext):
        """更改文件扩展名"""
        ext = os.path.splitext(filename)[1]
        return filename[:-len(ext)] + new_ext if ext else filename + new_ext

    def _fix_dir(self, file_path, base_dir):
        """修复文件路径为相对路径"""
        try:
            rel_path = os.path.relpath(file_path, base_dir)
            return rel_path.replace('\\', '/')
        except Exception:
            return file_path

    def _clean_component_configs(self, source_dir):
        """清理临时组件配置文件
        
        Args:
            source_dir: 源目录
        """
        try:
            component_configs = []
            for root, _, files in os.walk(source_dir):
                for file in files:
                    if (file.startswith("component_") or file.startswith("pages_")) and file.endswith(".json"):
                        component_configs.append(os.path.join(root, file))

            for file_path in component_configs:
                try:
                    os.remove(file_path)

                except Exception as e:
                    print(CONFIG_YAML.Colored().yellow(f"删除文件失败: {os.path.relpath(file_path, source_dir)}, 错误: {str(e)}"))

            # if not component_configs:
            # print(CONFIG_YAML.Colored().blue("未发现临时组件配置文件"))

        except Exception as e:
            print(CONFIG_YAML.Colored().yellow(f"清理临时组件配置文件时出错: {str(e)}"))
