# -*- coding: utf-8 -*-

import os
from .config import CONFIG_YAML
from .config_parser import ConfigParser
from .js_parser import JsParser
from .project_restorer import ProjectRestorer
from .wxss_parser import WxssParser


class ProjectParser:
    """微信小程序项目解析器"""

    _instance = None

    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = ProjectParser()
        return cls._instance

    def __init__(self):
        """初始化解析器"""
        self.colored = CONFIG_YAML.Colored()
        self.project_restorer = ProjectRestorer.get_instance()
        self.js_parser = JsParser()
        self.wxss_parser = WxssParser()
        self.config_parser = ConfigParser()

        self.parsers = {
            "config": self.config_parser.parse_config,
            "js": self.js_parser.parse_js,
            # "wxml": self.wxml_parser.parse_wxml,
            "wxss": self.wxss_parser.parse_wxss
        }

    def parse_project(self, source_dir, pretty=False, skip_parsers=None):
        """解析微信小程序项目
        
        Args:
            source_dir: 源目录
            pretty: 是否美化代码
            skip_parsers: 要跳过的解析器列表
            
        Returns:
            bool: 是否成功
        """
        try:

            if not os.path.exists(source_dir) or not os.path.isdir(source_dir):
                print(self.colored.red(f"目录不存在: {source_dir}"))
                return False

            skip_parsers = skip_parsers or []

            for parser_name, parser_func in self.parsers.items():
                if parser_name in skip_parsers:
                    print(self.colored.yellow(f"跳过 {parser_name} 解析"))
                    continue

                try:
                    parser_func(source_dir)
                except Exception as e:
                    print(self.colored.red(f"{parser_name} 解析失败: {str(e)}"))

            self.project_restorer.restore_project_structure(source_dir)

            if pretty:
                self._pretty_code(source_dir)

            return True

        except Exception as e:
            print(self.colored.red(f"解析微信小程序项目失败: {str(e)}"))
            return False

    def _pretty_code(self, source_dir):
        """美化代码"""
        try:
            print(self.colored.magenta("[*] 开始美化代码..."))

            try:
                from .formatter import Formatter
                formatter = Formatter()
                formatter.format_directory(source_dir)
                # print(self.colored.green("代码美化完成"))
            except ImportError:
                print(self.colored.yellow("警告: 未找到formatter模块，跳过代码美化"))

        except Exception as e:
            print(self.colored.red(f"美化代码失败: {str(e)}"))
