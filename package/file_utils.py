# -*- coding: utf-8 -*-

import os
import re


def extract_wxid_from_path(path):
    """从路径中提取wxid
    
    Args:
        path: 包含wxid的路径
        
    Returns:
        提取出的wxid
    """
    parts = path.replace('\\', '/').split('/')
    for part in parts:
        if part.startswith('wx'):
            return part
    return None


def find_wxapkg_files(directory, recursive=True):
    """查找目录中的wxapkg文件
    
    Args:
        directory: 要搜索的目录
        recursive: 是否递归搜索子目录
        verbose: 是否输出详细日志
        
    Returns:
        包含找到的wxapkg文件路径的列表
    """
    directory = os.path.abspath(directory)

    if not os.path.exists(directory):
        print(f"警告: 目录不存在 - {directory}")
        return []

    if not os.path.isdir(directory):
        print(f"警告: 路径不是目录 - {directory}")
        return []

    wxapkg_files = []

    try:
        if recursive:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if file.lower().endswith('.wxapkg'):
                        full_path = os.path.join(root, file)
                        wxapkg_files.append(full_path)
        else:

            for file in os.listdir(directory):
                if file.lower().endswith('.wxapkg'):
                    full_path = os.path.join(directory, file)
                    if os.path.isfile(full_path):
                        wxapkg_files.append(full_path)
    except PermissionError:
        print(f"权限错误: 无法访问目录 {directory}")
    except Exception as e:
        print(f"搜索目录时出错: {directory}, 错误: {str(e)}")

    return wxapkg_files


def ensure_dir_exists(path):
    """确保目录存在，如果不存在则创建
    
    Args:
        path: 目录路径
    """
    if not os.path.exists(path):
        os.makedirs(path)


def sort_wxapkg_files(wxapkg_files):
    """对wxapkg文件进行排序，确保主包先处理
    
    Args:
        wxapkg_files: wxapkg文件路径列表
        
    Returns:
        排序后的wxapkg文件列表，主包在前，子包在后
    """
    main_packages = []
    sub_packages = []

    for wxapkg_file in wxapkg_files:
        file_name = os.path.basename(wxapkg_file)
        if re.search(r'_\d+\.wxapkg$', file_name) and not file_name.endswith('_0.wxapkg'):
            sub_packages.append(wxapkg_file)
        else:
            main_packages.append(wxapkg_file)

    return main_packages + sub_packages


def get_output_dir(input_path, wxid=None, specified_output=None):
    """确定输出目录路径
    
    Args:
        input_path: 输入文件或目录路径
        wxid: 小程序ID，如果为None则尝试从路径中提取
        specified_output: 用户指定的输出目录，如果有的话
        
    Returns:
        确定的输出目录路径
    """
    if specified_output:
        return specified_output

    if not wxid:
        wxid = extract_wxid_from_path(input_path)
        if not wxid:
            return os.path.join(os.path.dirname(input_path), "wxapkg_unpacked")

    return os.path.join(os.path.dirname(input_path), f"{wxid}_unpacked")
