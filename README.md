# e0e1-wx-gui

![Platform](https://img.shields.io/badge/Platform-Windows_10%2F11-0078D4)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)
![GUI](https://img.shields.io/badge/GUI-PySide6-41CD52)

一款面向 Windows 的微信小程序本地分析 GUI 工具，提供小程序包监控、自动反编译、正则匹配、代码优化、DevTools CDP、路由查看、云函数分析以及常用加密解密辅助能力。

> 本项目仅用于授权安全研究、学习和调试场景，请勿用于未授权目标或违反相关法律法规的用途。

## 目录

- [项目简介](#项目简介)
- [主要能力](#主要能力)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [使用前必读](#使用前必读)
- [推荐使用流程](#推荐使用流程)
- [项目结构](#项目结构)
- [功能预览](#功能预览)
- [致谢](#致谢)

## 项目简介

`e0e1-wx-gui` 主要用于辅助分析本机运行中的微信小程序。工具会围绕小程序包捕获、反编译、代码检索、动态调试和云函数分析等场景提供图形化支持，降低手工整理和来回切换工具的成本。

如果你是第一次使用，建议先阅读 [tools.md](./tools.md) 中的配置说明，再启动程序。

## 主要能力

- 自动检测正在运行的小程序，并记录主包、分包等加密包信息。
- 自动反编译小程序源代码，便于后续审计和静态分析。
- 内置正则匹配、文件搜索和定位能力，支持快速跳转到目标内容。
- 支持对反编译后的代码进行格式化和可读性优化。
- 提供 DevTools CDP 调试辅助，方便接入浏览器调试链路。
- 支持读取小程序路由并辅助跳转到目标页面。
- 支持云函数静态扫描，并可手动触发目标云函数。
- 提供常用加密解密辅助能力，便于还原和分析数据。

## 环境要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10 / Windows 11 |
| Python | 3.10 及以上 |
| 微信环境 | 本机需存在受支持的微信小程序运行环境 |
| 当前配置覆盖版本 | `11581` - `19459` |

## 快速开始

进入项目目录后，建议先创建虚拟环境，再安装依赖并启动程序：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

启动后会打开 `e0e1-wx-gui` 图形界面。

## 使用前必读

首次使用请优先阅读 [tools.md](./tools.md)，其中包含：

- 微信小程序运行环境版本的确认方法
- 缺失配置文件时的补充方式
- 应用内目录配置说明
- 抓包/代理转发导致无法回连时的处理方法
- 各个核心功能的操作示例

## 推荐使用流程

1. 按照 [tools.md](./tools.md) 检查本机微信小程序运行环境版本是否受支持。
2. 启动程序后，在配置中确认加密包目录是否正确。
3. 打开目标微信小程序，让工具自动识别并生成对应卡片。
4. 根据需要使用反编译、搜索、DevTools、路由、云函数和调试功能。

## 项目结构

```text
e0e1-wx-gui/
├─ main.py                # 程序入口
├─ package/               # 核心功能与界面实现
├─ tools/                 # Hook 脚本与版本配置
├─ README.md              # 项目首页说明
└─ tools.md               # 配置与功能使用指南
```

## 功能预览

### 1. 小程序监控

工具会自动检测正在运行的小程序，并在界面中生成对应卡片，同时记录主包与分包信息。

![小程序监控](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777821912634-72c3f9a8-e1eb-4155-ab0e-d5c394145571.png)

### 2. 自动反编译与代码搜索

选择目标小程序后，可自动反编译源代码，并结合内置正则匹配、搜索和定位能力进行分析。

![自动反编译源代码](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777821948600-3161cdd7-19ee-453c-96f5-49994984db7a.png)

![正则匹配结果](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777822005062-fa6746a9-1749-474f-9e28-f8874edb5aa2.png)

### 3. 代码优化

开启代码优化后，程序会在后台尝试整理反编译结果，提高代码可读性。

![代码优化结果](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777822261997-fa3da399-8243-4036-915f-234cc9e14432.png)

### 4. DevTools CDP

提供 DevTools CDP 调试辅助能力，便于浏览器侧联动调试和分析。

![DevTools CDP](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777869887060-67219f03-c224-48f7-af66-94c42c99926e.png)

### 5. 路由查看与页面跳转

支持读取小程序路由信息，并辅助查看或跳转到目标页面。

![路由功能](https://cdn.nlark.com/yuque/0/2026/gif/36087401/1777873011735-5eea03db-aa57-4659-a1a7-89cc8dd0faa9.gif)

### 6. 云函数分析

支持云函数静态扫描，并可手动调用目标云函数以辅助验证。

![云函数调用](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777873145523-9c892564-2808-4f9f-8de1-016d20934cd6.png)

### 7. 加密解密辅助

内置常用加密解密辅助功能，便于还原与分析小程序相关数据。

![加密解密](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777874729401-241b4e29-e48e-41e2-9b40-63a754aeb2ac.png)

更详细的配置步骤和功能操作说明请查看 [tools.md](./tools.md)。

## 致谢

感谢以下开源项目提供的思路和能力支持：

- [r3x5ur/unveilr](https://github.com/r3x5ur/unveilr)
- [Ackites/KillWxapkg](https://github.com/Ackites/KillWxapkg)
- [x0tools/WeChatOpenDevTools](https://github.com/x0tools/WeChatOpenDevTools)
- [mrknow001/wx_sessionkey_decrypt](https://github.com/mrknow001/wx_sessionkey_decrypt)
- [JaveleyQAQ/WeChatOpenDevTools-Python](https://github.com/JaveleyQAQ/WeChatOpenDevTools-Python)
- [Spade-sec/First](https://github.com/Spade-sec/First)
