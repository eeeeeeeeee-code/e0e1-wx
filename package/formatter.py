# -*- coding: utf-8 -*-

import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor

from .config import CONFIG_YAML


class Formatter:
    """代码格式化基类"""

    def __init__(self):
        self.formatters = {}
        self.register_formatters()
        self.lock = threading.Lock()
        self.success_count = 0
        self.skip_count = 0
        self.error_count = 0

    def register_formatters(self):
        """注册各种文件类型的格式化器"""
        self.formatters = {
            '.js': self.format_js,
            '.json': self.format_json,
            '.html': self.format_html,
            '.wxml': self.format_html,
            '.wxss': self.format_css,
            '.css': self.format_css
        }

    def get_formatter(self, file_ext):
        """获取对应文件扩展名的格式化器"""
        return self.formatters.get(file_ext.lower())

    def format_file(self, file_path):
        """格式化单个文件"""
        try:
            _, ext = os.path.splitext(file_path)
            formatter = self.get_formatter(ext)

            if formatter is None:
                with self.lock:
                    self.skip_count += 1
                return False

            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            formatted_content = formatter(content)

            if formatted_content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(formatted_content)
                with self.lock:
                    self.success_count += 1
                return True
            else:
                with self.lock:
                    self.skip_count += 1
                return False

        except Exception as e:
            with self.lock:
                self.error_count += 1
            print(f"格式化文件 {file_path} 时出错: {str(e)}")
            return False

    def format_directory(self, directory, max_workers=None):
        """使用多线程格式化目录下的所有文件"""
        if max_workers is None:
            max_workers = CONFIG_YAML().max_workers if hasattr(CONFIG_YAML(), 'max_workers') else 10

        self.success_count = 0
        self.skip_count = 0
        self.error_count = 0

        file_paths = []
        for root, _, files in os.walk(directory):
            for file in files:
                _, ext = os.path.splitext(file)
                if ext.lower() in self.formatters:
                    file_paths.append(os.path.join(root, file))

        total_files = len(file_paths)
        # print(CONFIG_YAML.Colored().green(f"找到 {total_files} 个可格式化的文件"))

        if total_files == 0:
            return

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for i, _ in enumerate(executor.map(self.format_file, file_paths)):
                if (i + 1) % 20 == 0 or i + 1 == total_files:
                    print(CONFIG_YAML.Colored().green(f"[+] 格式化进度: {i + 1}/{total_files} ({(i + 1) / total_files * 100:.1f}%)"))

        # print(CONFIG_YAML.Colored().green(f"格式化完成: 成功 {self.success_count} 个文件, 跳过 {self.skip_count} 个文件, 失败 {self.error_count} 个文件"))

    def format_js(self, content):
        """格式化JavaScript代码"""
        try:
            import jsbeautifier
            opts = jsbeautifier.default_options()
            opts.indent_size = 2
            opts.indent_char = ' '
            opts.max_preserve_newlines = 2
            opts.preserve_newlines = True
            opts.keep_array_indentation = False
            opts.break_chained_methods = False
            opts.indent_scripts = "normal"
            opts.brace_style = "collapse"
            opts.space_before_conditional = True
            opts.unescape_strings = True
            opts.jslint_happy = False
            opts.end_with_newline = True
            opts.wrap_line_length = 0
            opts.indent_inner_html = False
            opts.comma_first = False
            opts.e4x = False
            opts.indent_empty_lines = False
            return jsbeautifier.beautify(content, opts)
        except ImportError:
            print("警告: jsbeautifier库未安装，跳过JS格式化")
            return content
        except Exception as e:
            print(f"JS格式化错误: {str(e)}")
            return content

    def format_json(self, content):
        """格式化JSON代码"""
        try:
            parsed = json.loads(content)
            return json.dumps(parsed, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"JSON格式化错误: {str(e)}")
            return content

    def format_html(self, content):
        """格式化HTML/WXML代码"""
        try:
            import html.parser
            import re
            script_pattern = re.compile(r'(<script[^>]*>)(.*?)(</script>)', re.DOTALL)
            def replace_script(match):
                script_tag_open = match.group(1)
                script_content = match.group(2)
                script_tag_close = match.group(3)

                formatted_js = self.format_js(script_content)
                return f"{script_tag_open}\n{formatted_js}\n{script_tag_close}"

            content = script_pattern.sub(replace_script, content)

            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(content, 'html.parser')
                return soup.prettify()
            except ImportError:
                print("警告: BeautifulSoup库未安装，使用简单格式化")

                content = re.sub(r'>\s+<', '>\n<', content)
                return content

        except Exception as e:
            print(f"HTML格式化错误: {str(e)}")
            return content

    def format_css(self, content):
        """格式化CSS/WXSS代码"""
        try:
            content = re.sub(r'\s+', ' ', content)
            content = re.sub(r'\s*{\s*', ' {\n    ', content)
            content = re.sub(r'\s*}\s*', '\n}\n', content)
            content = re.sub(r';\s*', ';\n    ', content)
            content = re.sub(r';\n\s*\}', ';\n}', content)
            return content
        except Exception as e:
            print(f"CSS格式化错误: {str(e)}")
            return content
