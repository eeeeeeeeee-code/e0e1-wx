# -*- coding: utf-8 -*-
import os
import re
from .config import CONFIG_YAML

class JsParser:
    """JavaScript文件解析器"""

    def __init__(self):

        try:
            import js2py
            self.js2py = js2py
        except ImportError:
            print(CONFIG_YAML.Colored().yellow("警告: 未安装js2py模块，JS解析功能可能受限"))
            print(CONFIG_YAML.Colored().yellow("请使用命令安装: pip install js2py"))
            self.js2py = None

        try:
            import execjs
            self.execjs = execjs
        except ImportError:
            self.execjs = None

    def parse_js(self, source_dir):
        """解析JS文件
        
        Args:
            source_dir: 源目录
            
        Returns:
            bool: 是否成功
        """
        try:

            app_service_path = os.path.join(source_dir, 'app-service.js')
            if not os.path.exists(app_service_path):

                alternative_files = ['app-service.js', 'appservice.js', 'game.js']
                found = False
                for alt_file in alternative_files:
                    alt_path = os.path.join(source_dir, alt_file)
                    if os.path.exists(alt_path):
                        app_service_path = alt_path
                        found = True
                        break

                if not found:
                    print(CONFIG_YAML.Colored().yellow("未找到app-service.js或替代文件，跳过JS解析"))
                    return False

            with open(app_service_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            params = self._extract_define_params(content)

            if not params:
                print(CONFIG_YAML.Colored().yellow("未找到define函数调用，尝试使用JavaScript引擎解析"))
                params = self._run_js_engine(content)

            if not params:
                print(CONFIG_YAML.Colored().yellow("未能提取JS模块，跳过JS解析"))
                return False

            for param in params:
                module_name = param['ModuleName']
                func_body = param['FuncBody']

                full_path = os.path.join(source_dir, module_name)

                os.makedirs(os.path.dirname(full_path), exist_ok=True)

                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(func_body)

            print(CONFIG_YAML.Colored().green("[+] JS文件解析完成"))
            return True

        except Exception as e:
            print(CONFIG_YAML.Colored().red(f"解析JS文件失败: {str(e)}"))
            return False

    def _extract_define_params(self, js_code):

        pattern = r'define\s*\(\s*["\'](.*?)["\']\s*,\s*function\s*\(([^)]*)\)\s*\{([\s\S]*?)\}\s*,\s*\{[^}]*isPage\s*:\s*[^}]*\}\s*\)\s*;'
        matches = re.findall(pattern, js_code)

        if not matches:
            return None

        results = []
        for match in matches:
            if len(match) >= 3:
                params = {
                    'ModuleName': match[0],
                    'FuncBody': self._clean_define_func(match[0], match[2])
                }
                results.append(params)

        return results

    def _clean_define_func(self, module_name, func_body):
        cleaned_code = func_body.strip()
        if cleaned_code.startswith('"use strict";') or cleaned_code.startswith("'use strict';"):
            cleaned_code = cleaned_code[13:].strip()

        return cleaned_code

    def _run_js_engine(self, js_code):
        results = []

        if self.js2py:
            try:
                results = self._run_js2py(js_code)
            except Exception as e:
                print(CONFIG_YAML.Colored().yellow(f"使用js2py解析失败: {str(e)}"))

        if not results and self.execjs:
            try:
                results = self._run_execjs(js_code)
            except Exception as e:
                print(CONFIG_YAML.Colored().yellow(f"使用execjs解析失败: {str(e)}"))

        if not results:
            results = self._extract_with_regex(js_code)

        return results

    def _run_js2py(self, js_code):
        """使用js2py运行JavaScript代码"""
        results = []

        patch = """
        var window={};var navigator={};navigator.userAgent="iPhone";window.screen={};
        document={getElementsByTagName:()=>{}};function require(){};var global={};var __wxAppCode__={};var __wxConfig={};
        var __vd_version_info__={};var $gwx=function(){};var __g={};
        """

        context = self.js2py.EvalJs()

        define_func = """
        function define(moduleName, func) {
            try {
                var funcBody = func.toString();
                // 提取函数体
                var match = funcBody.match(/^function\\s*\\([^)]*\\)\\s*\\{([\\s\\S]*)\\}$/);
                if (match && match[1]) {
                    // 去除严格模式声明
                    var body = match[1].trim();
                    if (body.startsWith('"use strict";') || body.startsWith("'use strict';")) {
                        body = body.substring(13).trim();
                    }
                    
                    // 保存结果
                    if (!window.defineResults) {
                        window.defineResults = [];
                    }
                    window.defineResults.push({
                        ModuleName: moduleName,
                        FuncBody: body
                    });
                }
            } catch (e) {
                console.error("Error in define:", e);
            }
        }
        """

        try:
            context.execute(patch)
            context.execute(define_func)
            context.execute(js_code)

            if hasattr(context, 'window') and hasattr(context.window, 'defineResults'):
                results = context.window.defineResults

        except Exception as e:
            # print(CONFIG_YAML.Colored().yellow(f"js2py执行错误: {str(e)}"))
            pass
        return results

    def _run_execjs(self, js_code):
        """使用execjs运行JavaScript代码"""
        results = []

        patch = """
        var window={};var navigator={};navigator.userAgent="iPhone";window.screen={};
        document={getElementsByTagName:()=>{}};function require(){};var global={};var __wxAppCode__={};var __wxConfig={};
        var __vd_version_info__={};var $gwx=function(){};var __g={};
        var defineResults = [];
        
        function define(moduleName, func) {
            try {
                var funcBody = func.toString();
                // 提取函数体
                var match = funcBody.match(/^function\\s*\\([^)]*\\)\\s*\\{([\\s\\S]*)\\}$/);
                if (match && match[1]) {
                    // 去除严格模式声明
                    var body = match[1].trim();
                    if (body.startsWith('"use strict";') || body.startsWith("'use strict';")) {
                        body = body.substring(13).trim();
                    }
                    
                    // 保存结果
                    defineResults.push({
                        ModuleName: moduleName,
                        FuncBody: body
                    });
                }
            } catch (e) {
                console.error("Error in define:", e);
            }
        }
        
        function getResults() {
            return defineResults;
        }
        """

        try:

            ctx = self.execjs.compile(patch)

            ctx.eval(js_code)

            results = ctx.call("getResults")

        except Exception as e:
            print(CONFIG_YAML.Colored().yellow(f"execjs执行错误: {str(e)}"))

        return results

    def _extract_with_regex(self, js_code):
        """使用正则表达式直接提取JS模块"""
        results = []

        pattern = r'define\s*\(\s*["\']([^"\']+)["\']\s*,\s*function\s*\([^)]*\)\s*\{([\s\S]*?)\}\s*(?:,\s*\{[^}]*\})?\s*\)\s*;'
        matches = re.findall(pattern, js_code)

        for match in matches:
            if len(match) >= 2:
                module_name = match[0]
                func_body = match[1].strip()

                if func_body.startswith('"use strict";') or func_body.startswith("'use strict';"):
                    func_body = func_body[13:].strip()

                results.append({
                    'ModuleName': module_name,
                    'FuncBody': func_body
                })

        return results
