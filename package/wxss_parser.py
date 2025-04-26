# -*- coding: utf-8 -*-
import os
import re

from .config import CONFIG_YAML


class WxssParser:
    """WXSS样式解析器"""

    def __init__(self):

        try:
            import js2py
            self.js2py = js2py
        except ImportError:
            print(CONFIG_YAML.Colored().yellow("警告: 未安装js2py模块，WXSS解析功能可能受限"))
            print(CONFIG_YAML.Colored().yellow("请使用命令安装: pip install js2py"))
            self.js2py = None

        try:
            import execjs
            self.execjs = execjs
        except ImportError:
            self.execjs = None

    def parse_wxss(self, source_dir):
        """解析WXSS文件
        
        Args:
            source_dir: 源目录
            
        Returns:
            bool: 是否成功
        """
        try:

            page_frame_path = os.path.join(source_dir, 'page-frame.html')
            if not os.path.exists(page_frame_path):

                alternative_files = ['app-wxss.js', 'page-frame.js', 'pageframe.js']
                found = False
                for alt_file in alternative_files:
                    alt_path = os.path.join(source_dir, alt_file)
                    if os.path.exists(alt_path):
                        page_frame_path = alt_path
                        found = True
                        break

                if not found:
                    print(CONFIG_YAML.Colored().yellow("未找到page-frame.html或替代文件，跳过WXSS解析"))
                    return False

            with open(page_frame_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            if page_frame_path.endswith('.html'):
                script_code = self._extract_script(content)
            else:
                script_code = content

            css_code = self._get_css(script_code)

            if not css_code:
                print(CONFIG_YAML.Colored().yellow("未找到CSS代码，跳过WXSS解析"))
                return False

            results = {}
            run_list = {}

            if os.path.exists(os.path.join(source_dir, 'app.wxss')):
                run_list[os.path.join(source_dir, 'app.wxss')] = css_code
            else:
                run_list[os.path.join(source_dir, 'app.wxss')] = css_code

            html_files = self._scan_html_files(source_dir)

            for html_file in html_files:
                try:
                    with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
                        html_content = f.read()

                    html_script = self._extract_script(html_content)
                    css_match = re.search(r'setCssToHead\(([\s\S]*?\.wxss"[\s\S]*?)\s*\)', html_script)

                    if css_match:
                        run_list[html_file] = css_match.group(0)
                except Exception as e:
                    print(CONFIG_YAML.Colored().yellow(f"处理HTML文件失败: {html_file}, 错误: {str(e)}"))

            for name, code in run_list.items():
                self._run_vm(name, code, results)

            for path, content in results.items():

                if not path.endswith('.wxss'):
                    path = self._change_ext(path, '.wxss')

                full_path = os.path.join(source_dir, path)

                os.makedirs(os.path.dirname(full_path), exist_ok=True)

                content = self._transform_css(content)

                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)

            print(CONFIG_YAML.Colored().green("[+] WXSS文件解析完成"))
            return True

        except Exception as e:
            # print(CONFIG_YAML.Colored().red(f"解析WXSS文件失败: {str(e)}"))
            return False

    def _scan_html_files(self, dir_path):
        html_files = []

        for root, _, files in os.walk(dir_path):
            for file in files:
                if file.endswith('.html') and file != 'page-frame.html':
                    file_path = os.path.join(root, file)
                    html_files.append(file_path)

                    suffixes = ['.appservice.js', '.common.js', '.webview.js']
                    for suffix in suffixes:
                        js_file = file_path.replace('.html', suffix)
                        if os.path.exists(js_file):
                            try:
                                os.remove(js_file)
                            except:
                                pass

        return html_files

    def _transform_css(self, css_content):

        css_content = re.sub(r'/\*[\s\S]*?\*/', '', css_content)

        css_content = re.sub(r'\s+', ' ', css_content)

        css_content = self._beautify_css(css_content)

        return css_content

    def _beautify_css(self, css_content):
        """美化CSS内容"""

        css_content = re.sub(r'(\{|\})', r'\1\n', css_content)

        css_content = re.sub(r';', ';\n', css_content)

        lines = css_content.split('\n')
        indent_level = 0
        result = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if '}' in line:
                indent_level = max(0, indent_level - 1)

            result.append('    ' * indent_level + line)

            if '{' in line:
                indent_level += 1

        return '\n'.join(result)

    def _extract_script(self, html_content):
        script_pattern = r'<script[^>]*>([\s\S]*?)<\/script>'
        scripts = re.findall(script_pattern, html_content)
        return '\n'.join(scripts)

    def _get_css(self, script_code):

        set_re = re.compile(r'setCssToHead\(([\s\S]*?)\.wxss"\s*\}\)')
        com_re = re.compile(r'__COMMON_STYLESHEETS__\[\'([^\']*\.wxss)\'\]\s*=\s*\[(.*?)\];')

        script_builder = []

        matches = set_re.findall(script_code)
        if matches:
            for match in matches:
                try:

                    last_pos = script_code.rfind('setCssToHead(')
                    if last_pos >= 0:
                        res = script_code[last_pos:]
                        script_builder.append(res)
                        script_builder.append(";\n")
                except Exception as e:
                    print(CONFIG_YAML.Colored().yellow(f"处理setCssToHead调用失败: {str(e)}"))

        matches = com_re.findall(script_code)
        if matches:
            for match in matches:
                try:
                    script_builder.append(f"__COMMON_STYLESHEETS__['{match[0]}'] = [{match[1]}];\n")
                except Exception as e:
                    print(CONFIG_YAML.Colored().yellow(f"处理COMMON_STYLESHEETS定义失败: {str(e)}"))

        return ''.join(script_builder)

    def _make_relative_path(self, base, target):
        try:
            base_dir = os.path.dirname(base)
            rel_path = os.path.relpath(target, base_dir)

            return rel_path.replace('\\', '/')
        except Exception:
            return target

    def _handle_el(self, el, k):
        if isinstance(el, list):
            if len(el) == 1 and el[0] == 1:
                return ""

            if el[0] == 0:
                return f"{el[1]}rpx"
            elif el[0] == 2:
                _el = el[1]
                path = ""

                if isinstance(_el, int):
                    return ""
                elif isinstance(_el, str):
                    path = _el
                elif isinstance(_el, list):
                    return self._handle_el(_el, k)
                else:
                    print(CONFIG_YAML.Colored().yellow(f"未处理的元素类型: {el}"))
                    return ""

                if not path:
                    return ""

                target = self._make_relative_path(k, path)
                if target:
                    return f'@import "{target}";\n'

                return ""
            else:
                print(CONFIG_YAML.Colored().yellow(f"未处理的数据: {el}"))
                return ""

        return str(el)

    def _style_conversion(self, path, content):
        result = ""
        for el in content:
            result += self._handle_el(el, path)
        return result

    def _run_vm(self, name, code, results):
        if self.js2py:
            self._run_js2py_vm(name, code, results)

        elif self.execjs:
            self._run_execjs_vm(name, code, results)
        else:
            print(CONFIG_YAML.Colored().yellow("警告: 未安装JavaScript执行引擎，无法解析WXSS内容"))

            self._extract_css_with_regex(code, results)

    def _run_js2py_vm(self, name, code, results):
        """使用js2py运行JavaScript虚拟机"""
        try:

            context = self.js2py.EvalJs({'results': results})

            context.execute("""
            var console = {
                log: function() {},
                error: function() {},
                warn: function() {}
            };
            
            // 安全的eval函数
            function safeEval(code) {
                try {
                    return eval(code);
                } catch (e) {
                    console.error("Eval error:", e);
                    return null;
                }
            }
            """)

            context.execute("""
            var __COMMON_STYLESHEETS__ = {};
            var window = {};
            var navigator = {userAgent: "iPhone"};
            window.screen = {};
            var document = {getElementsByTagName: function() { return []; }};
            
            function styleConversion(path, content) {
                var result = '';
                if (!content || !Array.isArray(content)) {
                    return result;
                }
                for (var i = 0; i < content.length; i++) {
                    result += handleEl(content[i], path);
                }
                return result;
            }
            
            function handleEl(el, k) {
                if (!el) return '';
                
                if (Array.isArray(el)) {
                    if (el.length === 0) return '';
                    if (el.length === 1 && el[0] === 1) return '';
                    
                    if (el[0] === 0 && el.length > 1) {
                        return el[1] + 'rpx';
                    } else if (el[0] === 2 && el.length > 1) {
                        var _el = el[1];
                        var path = '';
                        
                        if (typeof _el === 'number') {
                            return '';
                        } else if (typeof _el === 'string') {
                            path = _el;
                        } else if (Array.isArray(_el)) {
                            return handleEl(_el, k);
                        } else {
                            return '';
                        }
                        
                        if (!path) {
                            return '';
                        }
                        
                        return '@import "' + path + '";\n';
                    } else {
                        return '';
                    }
                }
                
                return String(el);
            }
            
            function setCssToHead(sources, options) {
                try {
                    if (!sources || !Array.isArray(sources) || sources.length === 0) {
                        return;
                    }
                    
                    var path = '';
                    if (options && options.path) {
                        path = options.path;
                    } else if (typeof options === 'string') {
                        path = options;
                    }
                    
                    if (!path) {
                        return;
                    }
                    
                    var result = styleConversion(path, sources);
                    if (!results[path]) {
                        results[path] = '';
                    }
                    results[path] += result;
                } catch (e) {
                    console.error("setCssToHead error:", e);
                }
            }
            """)

            try:

                code_chunks = self._split_code_into_chunks(code)
                for chunk in code_chunks:
                    try:
                        context.execute(chunk)
                    except Exception as chunk_error:
                        print(CONFIG_YAML.Colored().yellow(f"执行代码块失败，跳过: {str(chunk_error)[:100]}..."))
            except Exception as e:
                print(CONFIG_YAML.Colored().yellow(f"分段执行失败，尝试整体执行: {str(e)}"))
                try:
                    context.execute(code)
                except Exception as e2:
                    print(CONFIG_YAML.Colored().yellow(f"整体执行也失败: {str(e2)}"))

            try:
                common_stylesheets = getattr(context, '__COMMON_STYLESHEETS__', {})
                if common_stylesheets and hasattr(common_stylesheets, 'to_dict'):
                    common_stylesheets = common_stylesheets.to_dict()

                for path, sources in common_stylesheets.items():
                    if path not in results:
                        results[path] = ''

                    if hasattr(sources, 'to_list'):
                        sources = sources.to_list()

                    try:
                        result = context.eval(f"styleConversion('{path}', {sources})")
                        results[path] += result
                    except:

                        results[path] += self._style_conversion(path, sources)
            except Exception as e:
                print(CONFIG_YAML.Colored().yellow(f"处理COMMON_STYLESHEETS失败: {str(e)}"))

        except Exception as e:

            self._extract_css_with_regex(code, results)

    def _split_code_into_chunks(self, code, chunk_size=5000):
        """将代码分割成多个块，避免整体执行失败"""

        statements = re.split(r';(?![^{]*})', code)
        chunks = []
        current_chunk = ""

        for statement in statements:
            if len(current_chunk) + len(statement) > chunk_size:
                chunks.append(current_chunk + ";")
                current_chunk = statement
            else:
                current_chunk += statement + ";"

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _run_execjs_vm(self, name, code, results):
        """使用execjs运行JavaScript虚拟机"""
        try:

            js_env = """
            var __COMMON_STYLESHEETS__ = {};
            var window = {};
            var navigator = {userAgent: "iPhone"};
            window.screen = {};
            var document = {getElementsByTagName: function() { return []; }};
            var results = {};
            
            function setCssToHead(sources, options) {
                if (!sources || sources.length === 0) {
                    return;
                }
                
                var path = '';
                if (options && options.path) {
                    path = options.path;
                } else if (typeof options === 'string') {
                    path = options;
                }
                
                if (!path) {
                    return;
                }
                
                var result = styleConversion(path, sources);
                if (!results[path]) {
                    results[path] = '';
                }
                results[path] += result;
            }
            
            function styleConversion(path, content) {
                var result = '';
                for (var i = 0; i < content.length; i++) {
                    result += handleEl(content[i], path);
                }
                return result;
            }
            
            function handleEl(el, k) {
                if (Array.isArray(el)) {
                    if (el.length === 1 && el[0] === 1) {
                        return '';
                    }
                    
                    switch (el[0]) {
                        case 0:
                            return el[1] + 'rpx';
                        case 2:
                            var _el = el[1];
                            var path = '';
                            
                            if (typeof _el === 'number') {
                                return '';
                            } else if (typeof _el === 'string') {
                                path = _el;
                            } else if (Array.isArray(_el)) {
                                return handleEl(_el, k);
                            } else {
                                console.log('Unprocessed element found:', el);
                                return '';
                            }
                            
                            if (!path) {
                                return '';
                            }
                            
                            var target = makeRelativePath(k, path);
                            if (target) {
                                return '@import "' + target + '";\n';
                            }
                            
                            return '';
                        default:
                            console.log('Unprocessed data found:', el);
                            return '';
                    }
                }
                
                return String(el);
            }
            
            function makeRelativePath(base, target) {
                // 简单实现相对路径计算
                return target;
            }
            
            function getResults() {
                return results;
            }
            """

            ctx = self.execjs.compile(js_env)

            ctx.eval(code)

            js_results = ctx.call("getResults")

            for path, content in js_results.items():
                if path not in results:
                    results[path] = ''
                results[path] += content

            try:
                common_stylesheets = ctx.eval("__COMMON_STYLESHEETS__")

                for path, sources in common_stylesheets.items():
                    if path not in results:
                        results[path] = ''

                    result = ctx.call("styleConversion", path, sources)
                    results[path] += result
            except Exception as e:
                print(CONFIG_YAML.Colored().yellow(f"处理COMMON_STYLESHEETS失败: {str(e)}"))

        except Exception as e:
            # print(CONFIG_YAML.Colored().yellow(f"使用execjs运行JavaScript失败: {str(e)}"))

            self._extract_css_with_regex(code, results)

    def _extract_css_with_regex(self, css_code, results):
        """使用正则表达式直接提取CSS"""
        try:

            patterns = [
                r'setCssToHead\(\[(.*?)\],\s*{?path\s*:\s*[\'"]([^\'"]+)[\'"]',
                r'setCssToHead\(\[(.*?)\],\s*[\'"]([^\'"]+)[\'"]',
                r'__COMMON_STYLESHEETS__\[[\'"]([^\'"]+)[\'"]\]\s*=\s*\[(.*?)\];',

                r'setCssToHead\(\[([\s\S]*?)\],\s*(?:{[^}]*path\s*:\s*)?[\'"]([^\'"]+\.wxss)[\'"]',
                r'[\'"]([^\'\"]+\.wxss)[\'"][\s\S]*?content\s*:\s*[\'"]([^\'"]+)[\'"]'
            ]

            extracted = False

            for pattern in patterns:
                matches = re.finditer(pattern, css_code, re.DOTALL)

                for match in matches:
                    if len(match.groups()) == 2:
                        content_part = match.group(1)
                        path = match.group(2)

                        if not path.endswith('.wxss'):
                            path = self._change_ext(path, '.wxss')

                        if path not in results:
                            results[path] = ''

                        self._extract_css_content(content_part, path, results)
                        extracted = True

            if not extracted:

                css_patterns = [
                    r'[\'"]([^\'\"]*?{[^}]*}[^\'\"]*)[\'"]',
                    r'content\s*:\s*[\'"]([^\'\"]*?{[^}]*}[^\'\"]*)[\'"]',
                    r'[\'"]([^\'\"]*?[\w-]+\s*:\s*[^;]+;[^\'\"]*)[\'"]'
                ]

                for css_pattern in css_patterns:
                    css_matches = re.finditer(css_pattern, css_code, re.DOTALL)

                    for css_match in css_matches:
                        content = css_match.group(1)

                        if '{' in content and '}' in content or ';' in content:
                            if 'app.wxss' not in results:
                                results['app.wxss'] = ''

                            try:
                                content = content.encode().decode('unicode_escape')
                            except:
                                pass

                            results['app.wxss'] += content + '\n'
                            extracted = True

                if not extracted:

                    all_strings = re.findall(r'[\'"]([^\'"]{20,})[\'"]', css_code)
                    css_content = []

                    for string in all_strings:

                        if ('{' in string and '}' in string) or ';' in string:
                            try:
                                decoded = string.encode().decode('unicode_escape')
                                css_content.append(decoded)
                            except:
                                css_content.append(string)

                    if css_content:
                        results['app.wxss'] = '\n'.join(css_content)

        except Exception as e:
            print(CONFIG_YAML.Colored().yellow(f"正则提取CSS失败: {str(e)}"))

            try:
                css_like = re.findall(r'[{};]', css_code)
                if len(css_like) > 10:
                    results['app.wxss'] = css_code
            except:
                pass

    def _extract_css_content(self, content_part, path, results):
        """从内容部分提取CSS"""
        extracted = False

        content_matches = re.finditer(r'{content\s*:\s*[\'"]([^\'"]+)[\'"]', content_part)
        for content_match in content_matches:
            content = content_match.group(1)

            try:
                content = content.encode().decode('unicode_escape')
            except:
                pass
            results[path] += content
            extracted = True

        if not extracted:
            string_matches = re.finditer(r'[\'"]([^\'"]+)[\'"]', content_part)
            for string_match in string_matches:
                content = string_match.group(1)

                if '{' in content or '}' in content or ';' in content:
                    try:
                        content = content.encode().decode('unicode_escape')
                    except:
                        pass
                    results[path] += content
                    extracted = True

        return extracted

    def _change_ext(self, filename, new_ext):
        """更改文件扩展名"""
        ext = os.path.splitext(filename)[1]
        return filename[:-len(ext)] + new_ext
