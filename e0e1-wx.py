# -*- coding: utf-8 -*-
import argparse
import os
import mmap
import random
import re
import json
import string
import filetype
import requests
import shutil
import subprocess
import win32gui
import win32process
import psutil
import frida
import sys
import asyncio
import httpx
import threading
import pandas as pd
from colorama import Fore
from tqdm.asyncio import tqdm
from urllib.parse import urljoin, urlparse
from yaml import safe_load
from time import sleep
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests_toolbelt import MultipartEncoder

requests.packages.urllib3.disable_warnings()


class CONFIG:
    def __init__(self):
        config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
        config = safe_load(open(config_path, "r").read())
        self.wx_file = config["wx-tools"]["wx-file"]

        self.feishutf = config["bot"]["feishu-tf"]
        self.app_id = config["bot"]["api_id"]
        self.app_secret = config["bot"]["api_secret"]
        self.phone = config["bot"]["phone"]

        self.asyncio_http_tf = config["tools"]["asyncio_http_tf"]
        self.proess_file = config["tools"]["proess_file"]


class CONFIG_YAML:
    def __init__(self):
        config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
        config = safe_load(open(config_path, "r").read())

        self.not_asyncio_http = config["tools"]["not_asyncio_http"]
        self.not_asyncio_port = config["tools"]["not_asyncio_stats"]
        self.max_workers = config["tools"]["max_workers"]

        self.req_header = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.8',
        }

        self._regex = {
            'google_api': r'AIza[0-9A-Za-z-_]{35}',
            'firebase': r'AAAA[A-Za-z0-9_-]{7}:[A-Za-z0-9_-]{140}',
            'google_captcha': r'6L[0-9A-Za-z-_]{38}|^6[0-9a-zA-Z_-]{39}$',
            'google_oauth': r'ya29\.[0-9A-Za-z\-_]+',
            'amazon_aws_access_key_id': r'A[SK]IA[0-9A-Z]{16}',
            'amazon_mws_auth_toke': r'amzn\\.mws\\.[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            'amazon_aws_url': r's3\.amazonaws.com[/]+|[a-zA-Z0-9_-]*\.s3\.amazonaws.com',
            'amazon_aws_url2': r"("
                               r"[a-zA-Z0-9-\.\_]+\.s3\.amazonaws\.com"
                               r"|s3://[a-zA-Z0-9-\.\_]+"
                               r"|s3-[a-zA-Z0-9-\.\_\/]+"
                               r"|s3.amazonaws.com/[a-zA-Z0-9-\.\_]+"
                               r"|s3.console.aws.amazon.com/s3/buckets/[a-zA-Z0-9-\.\_]+)",
            'facebook_access_token': r'EAACEdEose0cBA[0-9A-Za-z]+',
            'authorization_basic': r'basic [a-zA-Z0-9=:_\+\/-]{5,100}',
            'authorization_bearer': r'bearer [a-zA-Z0-9_\-\.=:_\+\/]{5,100}',
            'authorization_api': r'api[key|_key|\s+]+[a-zA-Z0-9_\-]{5,100}',
            'mailgun_api_key': r'key-[0-9a-zA-Z]{32}',
            'twilio_api_key': r'SK[0-9a-fA-F]{32}',
            'paypal_braintree_access_token': r'access_token\$production\$[0-9a-z]{16}\$[0-9a-f]{32}',
            'stripe_standard_api': r'sk_live_[0-9a-zA-Z]{24}',
            'stripe_restricted_api': r'rk_live_[0-9a-zA-Z]{24}',
            'github_access_token': r'[a-zA-Z0-9_-]*:[a-zA-Z0-9_\-]+@github\.com*',
            'json_web_token': r'ey[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*$',
            'Heroku API KEY': r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',
            'username&password': r"""(?i)\b(password|pwd|passwd|username|user|admin_pass|admin_user)\s*[:=]\s*(['"]?)([^'"\s]+)\2""",
            'key': r"""(?i)\b(key|key_login|jwtkey|AESKEY|appid|AES_KEY|appsecret|app_secret|Authorization|access_token|algolia_admin_key|algolia_api_key|alias_pass|alicloud_access_key|amazon_secret_access_key|amazonaws|ansible_vault_password|aos_key|api_key|api_key_secret|api_key_sid|api_secret|apikey|apiSecret|app_debug|app_id|app_key|app_log_level|app_secret|appkey|appkeysecret|application_key|appspot)\s*[:=]\s*(['"]?)([^'"\s]+)\2""",
            "ak/sk": r"""(?i)\b(accesskeyid|accesskeysecret|access_key|ak|sk)\s*[:=]\s*(['"]?)([^'"\s]+)\2""",
            "身份证号": r"[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]",
            "手机号&座机号&": r"(?:1[3-9]\d{9})|(?:0\d{2,3}-?\d{7,8})",
            "邮箱": r"\b[\w.-]+@[\w.-]+\.\w+\b",
            "ditu_key": "webapi.amap.com|api.map.baidu.com|apis.map.qq.com|map.qq.com/api/|maps.googleapis.com",
            "google_outh_url": "[0-9]+-[0-9A-Za-z_]{32}.apps.googleusercontent.com",
            "AWS_GraphQL": "da2-[a-z0-9]{26}",
        }

        self.pattern_raw = r"""
          (?:"|')
          (
            ((?:[a-zA-Z]{1,10}://|//)
            [^"'/]{1,}\.
            [a-zA-Z]{2,}[^"']{0,})
            |
            ((?:/|\.\./|\./)
            [^"'><,;| *()(%%$^/\\\[\]]
            [^"'><,;|()]{1,})
            |
            ([a-zA-Z0-9_\-/]{1,}/
            [a-zA-Z0-9_\-/]{1,}
            \.(?:[a-zA-Z]{1,4}|action)
            (?:[\?|/][^"|']{0,}|))
            |
            ([a-zA-Z0-9_\-]{1,}
            \.(?:php|asp|aspx|jsp|json|action|html|js|txt|xml)
            (?:\?[^"|']{0,}|))
          )
          (?:"|')
        """

    class Colored(object):
        def red(self, s):
            return Fore.RED + s + Fore.RESET

        def green(self, s):
            return Fore.GREEN + s + Fore.RESET

        def yellow(self, s):
            return Fore.YELLOW + s + Fore.RESET

        def blue(self, s):
            return Fore.BLUE + s + Fore.RESET

        def magenta(self, s):
            return Fore.MAGENTA + s + Fore.RESET

    @property
    def regex(self):
        return self._regex


class LargeFileProcessor:
    def __init__(self):
        config = CONFIG_YAML()
        self.pattern = re.compile(bytes(config.pattern_raw, 'utf-8'), re.VERBOSE)
        self._compiled_regex = {regex_name: re.compile(bytes(regex_pattern, "utf-8"), re.VERBOSE) for regex_name, regex_pattern in config._regex.items()}
        self.path_list = []
        self.reges_list = []
        self.asyncio_http = []
        self.asyncio_path = []
        self.existing_matches = set()
        self.not_asyncio_http = config.not_asyncio_http
        self.lock = threading.Lock()

    def is_image(self, filepath):
        try:
            kind = filetype.guess(filepath)
            if kind is None:
                return True
            if kind.mime.startswith('image/'):
                return False
            print(CONFIG_YAML.Colored().blue(f"特殊文件：{filepath}"))
        except:
            return True

    def path_process_file(self, file_path):
        try:
            with open(file_path, 'r') as file:
                with mmap.mmap(file.fileno(), length=0, access=mmap.ACCESS_READ) as mm:
                    unique_matches = {match[0].decode('utf-8') for match in self.pattern.findall(mm)}
                    new_matches = [match for match in unique_matches if match not in self.existing_matches and not any(img in match for img in [".jpg",".png",".jpeg",".gif"]) ]
                    with self.lock:
                        self.path_list.extend([[file_path, match] for match in new_matches])
                        self.existing_matches.update(new_matches)
        except Exception as e:
            pass
            # print(CONFIG_YAML.Colored().red(f"LargeFileProcessor/path_process_file bug: {e}"))

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
            # print(CONFIG_YAML.Colored().red(f"LargeFileProcessor/reges_process_file bug: {e}"))

    def path_process_directory(self, directory_path, folder_file):
        print(CONFIG_YAML.Colored().green("开始搜索接口和泄露"))
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

        self.path_list.sort(key=self.custom_sort)
        self.reges_list = deduplicate0(self.reges_list)

        http_combins = Asyncio_requ().combine_urls(self.asyncio_http, self.asyncio_path)
        title = folder_file.split("/")[2]
        xlsx_file = folder_file + "/" + CONFIG().proess_file
        Process_Print(xlsx_file).all_xlsx_file(self.path_list, ['文件位置', '泄露地址'], "接口")

        try:
            Process_Print(xlsx_file).add_xlsx_file(self.reges_list, ['文件位置', '泄露key', '泄露内容'], "key")
        except:
            Process_Print(xlsx_file).add_xlsx_file([["", "", ""]], ['文件位置', '泄露key', '泄露内容'], "key")

        try:
            Process_Print(xlsx_file).three_process_fuzz(http_combins)
        except:
            Process_Print(xlsx_file).three_process_fuzz([[""]])

        if CONFIG().asyncio_http_tf:
            result_http = asyncio.get_event_loop().run_until_complete(Asyncio_requ().filter_urls(http_combins))
            Process_Print(xlsx_file).add_xlsx_file(result_http, ['状态码', '大小', '接口url'], "fuzz")

        if CONFIG().feishutf:
            feishu_rebot("{}-小程序 接口和泄露扫描完毕".format(title), CONFIG().proess_file, xlsx_file)
        print(CONFIG_YAML.Colored().green("接口请求完成,文件保存到{}".format(xlsx_file)))

    def custom_sort(self, item):
        if item[1].startswith("http"):
            if all(not_http not in item[1] for not_http in self.not_asyncio_http):
                with self.lock:
                    self.asyncio_http.append(item[1])
                return 0, item[1]
        elif not item[1].startswith('.'):
            with self.lock:
                self.asyncio_path.append(item[1])
            return 1, item[1]
        return 2, item[1]


class Asyncio_requ:
    def __init__(self):
        self.http_combins = []
        self.result_http = []

    def extract_url(self, url):
        self.http_combins.append(url)
        parsed_url = urlparse(url)
        return f"{parsed_url.scheme}://{parsed_url.netloc}/"

    def combine_urls(self, urls, directories):
        base_urls = {self.extract_url(url) for url in urls}
        combined_list = [urljoin(base_url, directory.lstrip('/'))
                         for base_url in base_urls
                         for directory in directories]
        for com_http in combined_list:
            self.http_combins.append(com_http)
        return self.http_combins

    async def fetch_url(self, client, url):
        try:
            response = await client.get(url, timeout=2)
            status_code = response.status_code
            size = len(response.content) if 'Content-Length' not in response.headers else int(response.headers['Content-Length'])
            return status_code, size, url
        except httpx.ReadTimeout:
            return "timeout", 0, url
        except httpx.HTTPError as e:
            return "error", 0, url

    async def filter_urls(self, urls):
        try:
            async with httpx.AsyncClient(verify=False) as client:
                tasks = [asyncio.create_task(self.fetch_url(client, url)) for url in urls]
                results = []

                for result in tqdm(await asyncio.gather(*tasks, return_exceptions=True), total=len(tasks)):
                    results.append(result)

            self.result_http = [r for r in results if not isinstance(r, Exception) and r[0] not in CONFIG_YAML().not_asyncio_port]
            self.result_http.sort(key=lambda x: (x[0], x[1], x[2]) if isinstance(x[0], int) else (float('inf'), x[1], x[2]))
            return self.result_http
        except Exception as e:
            print(CONFIG_YAML.Colored().red(str(e)))


class Process_Print:
    def __init__(self, file_path):
        self.file_path = file_path

    def three_process_fuzz(self, data):
        series_data = pd.Series(data)
        df = pd.DataFrame({'接口': series_data})
        with pd.ExcelWriter(self.file_path, engine="openpyxl", mode='a', if_sheet_exists="overlay") as writer:
            df.to_excel(writer, sheet_name='拼接', index=False)

    def all_xlsx_file(self, data, columns_name, sheet_name):
        df = pd.DataFrame.from_records(data)
        df.columns = columns_name
        with pd.ExcelWriter(self.file_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=sheet_name, engine='xlsxwriter', index=False)

    def add_xlsx_file(self, data, columns_name, sheet_name):
        df = pd.DataFrame.from_records(data)
        df.columns = columns_name
        with pd.ExcelWriter(self.file_path, engine="openpyxl", mode='a', if_sheet_exists="overlay") as writer:
            df.to_excel(writer, sheet_name=sheet_name, engine='xlsxwriter', index=False)


class Wx_tools:
    def __init__(self):
        self.root_path = CONFIG().wx_file + "/Applet"
        self.root_path2 = CONFIG().wx_file + "\\Applet"
        self.unveilr = r".\tools\unveilr.exe"

    def remove_file_wx(self):
        try:
            with os.scandir(self.root_path) as entries:
                for entry in entries:
                    if entry.is_dir() and entry.name.startswith('wx') and len(entry.name) == 18:
                        shutil.rmtree(entry.path)
        except Exception as e:
            print(CONFIG_YAML.Colored().red(str(e)))

    def wx_file_wxapkg(self, path):
        current_path = path
        while True:
            entries = os.listdir(current_path)
            directories = [entry for entry in entries if os.path.isdir(os.path.join(current_path, entry))]
            if not directories:
                return current_path
            current_path = os.path.join(current_path, directories[0])

    def run_with_retry(self, command, max_retries=4):
        retry = 0
        success = False
        while retry < max_retries and not success:
            try:
                subprocess.run(command, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                success = True
            except subprocess.CalledProcessError:
                print(CONFIG_YAML.Colored().red("反编译工具出现错误，正在重试"))
                retry += 1

        if not success:
            print(CONFIG_YAML.Colored().red("达到最大重试次数，停止该次循环"))
            return True

    def monitor_new_wx(self, timeout=0.2):
        try:
            original_dirs = {entry.name for entry in os.scandir(self.root_path) if entry.is_dir()}
            sleep(timeout)
            new_dirs = {entry.name for entry in os.scandir(self.root_path) if entry.is_dir()}
            new_folders = new_dirs - original_dirs
            for folder in new_folders:
                wx_window_info = WX_HOOK().get_wechat_windows_info()
                window_text, pid, process_name = wx_window_info[0]
                if window_text == "HintWnd":
                    print(CONFIG_YAML.Colored().blue("\n检测到HintWnd，代表没有抓到小程序名，为不影响程序，这里使用随机数"))
                    window_text = window_text+"-"+''.join(random.choice(string.ascii_letters + string.digits) for _ in range(8))
                folder_file = "./result/{}".format(window_text)
                wxapkg_file = self.wx_file_wxapkg(self.root_path2 + '\\' + folder)
                if os.path.isdir(folder_file):
                    print(CONFIG_YAML.Colored().green(f"\n《{window_text}》文件已经存在"))
                else:
                    print(CONFIG_YAML.Colored().green("\n检测打开了 《{}》小程序正在进行反编译".format(window_text)))
                    os.mkdir(folder_file)
                    if self.run_with_retry("{} wx \"{}\" -o \"{}\"".format(self.unveilr, wxapkg_file, folder_file)):
                        os.rmdir(folder_file)
                        Wx_tools().remove_file_wx()
                        break
                    print(CONFIG_YAML.Colored().green("执行完毕-反编译源代码输出: {}".format(folder_file)))

                    if args.devtools_hook:
                        thread = threading.Thread(target=run_wechat_hook)
                        thread.start()

                    LargeFileProcessor().path_process_directory(folder_file, folder_file)
        except Exception as e:
            print(CONFIG_YAML.Colored().red("Wx_tools/monitor_new_wx bug: {}".format(e)))


class WX_HOOK:
    def __init__(self, js_path=r"./tools/WeChatAppEx.exe.js"):
        self.hook_js_path = js_path
        self.session = None

    def get_wechat_windows_info(self):
        try:
            window_info = []

            def callback(hwnd, extra):
                window_text = win32gui.GetWindowText(hwnd)
                if window_text:
                    pid = win32process.GetWindowThreadProcessId(hwnd)
                    process = psutil.Process(pid[1])
                    if process.name() == "WeChatAppEx.exe" and window_text not in ["微信", "MSCTFIME UI", "Default IME"]:
                        window_info.append((window_text, pid[1], process.name()))

            win32gui.EnumWindows(callback, None)

            return window_info
        except Exception as e:
            print(CONFIG_YAML.Colored().red("WX_HOOK/get_wechat_windows_info bug: {}".format(e)))

    def hook_wechat(self, on_message):
        window_info = self.get_wechat_windows_info()
        if window_info:
            window_text, pid, process_name = window_info[0]
            print(CONFIG_YAML.Colored().green("Window Title: {}, PID: {}, Process Name: {}".format(window_text, pid, process_name)))
            try:
                self.session = frida.attach(pid)
                with open(self.hook_js_path, 'r', encoding='utf8') as f:
                    script = self.session.create_script(f.read())

                script.on('message', on_message)
                script.load()
                sys.stdin.read()
            except KeyboardInterrupt:
                print(CONFIG_YAML.Colored().red('Detaching from process...'))
            finally:
                if self.session is not None:
                    self.session.detach()
        else:
            print(CONFIG_YAML.Colored().red("检测小程序没有打开"))


def on_message(message, data):
    if message['type'] == 'send':
        print(CONFIG_YAML.Colored().green("[*] {0}".format(message['payload'])))
    else:
        print(CONFIG_YAML.Colored().green(str(message)))


def run_wechat_hook():
    WX_HOOK().hook_wechat(on_message)


class FeishuTalk:
    def __init__(self):
        self.feishutf = CONFIG().feishutf
        self.app_id = CONFIG().app_id
        self.app_secret = CONFIG().app_secret
        self.phone = CONFIG().phone

        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
        }
        payload_data = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        response = requests.post(url=url, data=json.dumps(payload_data), headers=headers, verify=False).json()
        self.token = response['tenant_access_token']

    def uploadDocument(self, document_name, document_path):
        document_key_headers = {
            'Authorization': 'Bearer ' + self.token,
        }
        get_files_key_url = "https://open.feishu.cn/open-apis/im/v1/files"
        form = {'file_type': 'stream',
                'file_name': document_name,
                'file': (document_name, open(document_path, 'rb'), 'text/plain')}
        multi_form = MultipartEncoder(form)
        document_key_headers['Content-Type'] = multi_form.content_type
        response = requests.request("POST", get_files_key_url, headers=document_key_headers, data=multi_form, verify=False).json()
        files_key = response['data']['file_key']
        return files_key

    def user_id_info(self):
        headers = {
            'Authorization': 'Bearer ' + self.token,
            'Content-Type': 'application/json'
        }
        form = {
            "mobiles": self.phone
        }
        respose = requests.post("https://open.feishu.cn/open-apis/contact/v3/users/batch_get_id?user_id_type=open_id",
                                data=json.dumps(form), headers=headers, verify=False).text
        return json.loads(respose)['data']['user_list'][0]['user_id']

    def send_text(self, exp_print):
        if self.feishutf:
            url = "https://open.feishu.cn/open-apis/im/v1/messages"
            user_id = self.user_id_info()
            params = {"receive_id_type": "open_id"}
            msgContent = {
                "text": exp_print
            }
            req = {
                "receive_id": user_id,
                "msg_type": "text",
                "content": json.dumps(msgContent)
            }
            headers = {
                'Authorization': 'Bearer ' + self.token,
                'Content-Type': 'application/json'
            }
            payload = json.dumps(req)
            response = requests.request("POST", url, params=params, headers=headers, data=payload, verify=False)

            response.raise_for_status()
            response.json()

    def send_file(self, file_name, file_path):
        if self.feishutf:
            url = "https://open.feishu.cn/open-apis/im/v1/messages"
            user_id = self.user_id_info()
            params = {"receive_id_type": "open_id"}
            fileContent = {
                "file_key": self.uploadDocument(file_name, file_path)
            }
            req = {
                "receive_id": user_id,
                "msg_type": "file",
                "content": json.dumps(fileContent)
            }
            headers = {
                'Authorization': 'Bearer ' + self.token,
                'Content-Type': 'application/json'
            }
            payload = json.dumps(req)
            response = requests.request("POST", url, params=params, headers=headers, data=payload, verify=False)

            response.raise_for_status()
            response.json()


def feishu_rebot(send_text, send_file_name, send_file):
    try:
        FeishuTalk().send_text(send_text)
        FeishuTalk().send_file(send_file_name, send_file)
    except Exception as e:
        print(CONFIG_YAML.Colored().red("rebot/fieshu_rebot bug: " + str(e)))


def args_port():
    try:
        parser = argparse.ArgumentParser(description='File input')
        parser.add_argument('-hook', '--hook', dest='devtools_hook', action='store_true', help='启用hook,打开devtools')
        args = parser.parse_args()
        return args
    except Exception as e:
        print(CONFIG_YAML.Colored().red("args_port bugs: {}".format(e)))


if __name__ == "__main__":
    global args
    args = args_port()
    print(CONFIG_YAML.Colored().green('''
     ------------------------------------------
    |        ___       _                       |
    |   ___ / _ \  ___/ |    __      ____  __  |
    |  / _ \ | | |/ _ \ |____\ \ /\ / /\ \/ /  |
    | |  __/ |_| |  __/ |_____\ V  V /  >  <   |
    |  \___|\___/ \___|_|      \_/\_/  /_/\_\  |
    |           -- by: eeeeee --               |         
    | -- 该工具仅用于学习参考，均与作者无关 -- |              
     ------------------------------------------
    |https://github.com/eeeeeeeeee-code/e0e1-wx|
     ------------------------------------------
     '''))

    wx_tools = Wx_tools()
    wx_tools.remove_file_wx()
    print(CONFIG_YAML.Colored().magenta("e0e1-wx工具初始化成功~~\n注:不要快速切换小程序~~"))
    while True:
        wx_tools.monitor_new_wx()
