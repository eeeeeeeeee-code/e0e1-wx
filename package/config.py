# -*- coding: utf-8 -*-

import os
from yaml import safe_load
from colorama import Fore


class CONFIG:
    def __init__(self):
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
        try:
            config = safe_load(open(config_path, "r", encoding="gb18030").read())
        except:
            config = safe_load(open(config_path, "r", encoding="utf-8").read())

        self.wx_file = config["wx-tools"]["wx-file"]
        self.proess_file = config["tools"]["proess_file"]


class CONFIG_YAML:
    def __init__(self):
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
        try:
            config = safe_load(open(config_path, "r", encoding="gb18030").read())
        except:
            config = safe_load(open(config_path, "r", encoding="utf-8").read())
        self.max_workers = config["tools"]["max_workers"]

        self.req_header = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.8',
        }

        self._regex = config.get("rekey", {})

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

        def cran(self,s):
            return Fore.CYAN + s + Fore.RESET

    @property
    def regex(self):
        return self._regex