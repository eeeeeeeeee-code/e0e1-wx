# -*- coding: utf-8 -*-

import argparse
import os

from .config import CONFIG_YAML
from .wx_tools import Wx_tools
from .crypt_tools import CryptTools


def args_port():
    """解析命令行参数"""
    try:
        parser = argparse.ArgumentParser(description='File input')
        parser.add_argument('-hook', '--hook', dest='devtools_hook', action='store_true', help='启用hook,打开devtools')
        parser.add_argument('-pretty', '-p', dest='pretty_tf', action='store_true', help='启用代码优化,优化输出代码格式,注意部分小程序美化可能需较长时间')
        parser.add_argument('-restore', '-r', dest='restore_project', action='store_true', help='启用项目结构还原,还原小程序源代码结构')
        parser.add_argument('-crypt', '-c', dest='crypt_mode', choices=['encrypt', 'decrypt'], help='启用加解密功能: encrypt(加密) 或 decrypt(解密)')
        args = parser.parse_args()
        return args
    except Exception as e:
        print(CONFIG_YAML.Colored().red("args_port bugs: {}".format(e)))


if __name__ == "__main__":

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
    |                版本: 2.00                 |   
     ------------------------------------------
     '''))
    os.makedirs("./result", exist_ok=True)

    if args.crypt_mode:
        if args.crypt_mode == 'encrypt':
            CryptTools().run_encrypt_mode()
        elif args.crypt_mode == 'decrypt':
            CryptTools().run_decrypt_mode()
        exit(0)

    wx_tools = Wx_tools()
    wx_tools.remove_file_wx()
    print(CONFIG_YAML.Colored().magenta("[+] e0e1-wx工具初始化成功~~"))
    while True:
        wx_tools.monitor_new_wx(args=args)
