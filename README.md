# e0e1-wx-gui

一款面向 Windows 的微信小程序本地分析 GUI 工具，提供小程序包监控、自动反编译、正则匹配、代码优化、DevTools CDP、路由查看、云函数分析以及加密解密等能力。

> 本项目仅用于授权安全研究、学习和调试场景。请勿用于未授权目标或违反相关法律法规的用途。

## 目录

- [功能特性](#功能特性)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [微信小程序版本配置](#微信小程序版本配置)
- [应用配置](#应用配置)
- [功能说明](#功能说明)
- [致谢](#致谢)

## 功能特性

- 自动检测微信小程序运行状态，并记录主包、分包等加密包信息。
- 自动反编译微信小程序源代码。
- 支持正则规则扫描，双击匹配结果可跳转到对应字段。
- 支持对反编译后的代码进行格式化和优化。
- 支持 DevTools CDP 相关调试能力。
- 支持小程序路由查看和跳转辅助。
- 支持云函数静态扫描，并可选择调用对应云函数。
- 提供常用加密解密辅助功能。

## 环境要求

- 操作系统：Windows 10 / Windows 11
- Python：3.10+
- 微信：需存在受支持的微信小程序运行环境版本

## 快速开始

进入项目目录后，建议先创建虚拟环境，再安装依赖并启动程序。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

启动后会打开 `e0e1-wx-gui` 图形界面。

## 微信小程序版本配置

程序需要根据本机微信小程序运行环境版本加载对应的 Frida 配置。当前文档记录的支持版本范围为 `11581` 到 `19459`。

微信小程序运行环境目录通常位于：

```text
C:\Users\<本机用户名>\AppData\Roaming\Tencent\xwechat\XPlugin\Plugins\RadiumWMPF
```

可在该目录下查看当前小程序运行环境版本。

![查看微信小程序版本](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777875799638-6b5855b1-4537-498d-ad4c-ee157d881ca0.png)

如果目录中存在多个小程序版本，建议退出微信后清理旧的小程序运行环境文件，再重新打开微信生成当前版本文件。

如果当前微信小程序版本过高，或本项目缺少对应版本配置，可以从以下仓库下载新版本对应的配置文件：

[evi0s/WMPFDebugger - frida/config](https://github.com/evi0s/WMPFDebugger/tree/main/frida/config)

下载后将对应配置放入本项目目录：

```text
e0e1-wx-gui\tools\config\win
```

配置文件命名示例：

```text
addresses.19459.json
```

## 应用配置

在程序配置中设置微信小程序加密包目录。默认路径通常为：

```text
C:\Users\<本机用户名>\AppData\Roaming\Tencent\xwechat\radium\Applet\packages
```

![配置小程序加密文件位置](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777874359415-5e903826-7b85-4f3b-891f-b12b2ae503c2.png)

## 功能说明

### 小程序监控

程序会自动检测正在运行的小程序，并在界面中生成对应卡片。记录内容包括小程序源代码加密包，分包也会被记录。

![小程序监控](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777821912634-72c3f9a8-e1eb-4155-ab0e-d5c394145571.png)

### 自动反编译源代码

选择目标小程序后，可自动反编译小程序源代码，便于后续审计和分析。

![自动反编译源代码](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777821948600-3161cdd7-19ee-453c-96f5-49994984db7a.png)

### 正则匹配

内置正则匹配功能，可自动扫描关键内容。双击匹配结果后，可以跳转到对应字段位置。

![正则匹配结果](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777822005062-fa6746a9-1749-474f-9e28-f8874edb5aa2.png)

![正则匹配定位](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777822089662-61ba2680-a444-4dbd-823f-34fd31de5e9e.png)

正则规则可在规则配置中自定义。

![正则规则配置](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777822115383-4a5314f9-c46f-4f5b-a883-cd6f48a55731.png)

### 代码优化

开启代码优化后，程序会在后台尝试优化小程序反编译后的代码，提高可读性。

![代码优化开关](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777822206809-8f74bdeb-d101-4534-861e-d81191c66a15.png)

![代码优化结果](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777822261997-fa3da399-8243-4036-915f-234cc9e14432.png)

### DevTools CDP

提供 DevTools CDP 相关能力，辅助进行小程序调试和分析。

![DevTools CDP](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777869887060-67219f03-c224-48f7-af66-94c42c99926e.png)

![DevTools CDP 详情](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777869912236-f531706e-ce1e-48fa-8142-94920b40a843.png)

### 路由功能

支持读取小程序路由信息，并辅助查看或跳转页面。

![路由功能](https://cdn.nlark.com/yuque/0/2026/gif/36087401/1777873011735-5eea03db-aa57-4659-a1a7-89cc8dd0faa9.gif)

### 云函数功能

支持对云函数进行静态扫描。双击对应云函数后，可以选择调用目标云函数。

![云函数扫描](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777873103563-b665d67f-5756-44c8-837d-1062c342c2ae.png)

![云函数调用](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777873145523-9c892564-2808-4f9f-8de1-016d20934cd6.png)

### 加密解密

提供常用加密解密辅助功能，便于对小程序相关数据进行分析。

![加密解密](https://cdn.nlark.com/yuque/0/2026/png/36087401/1777874729401-241b4e29-e48e-41e2-9b40-63a754aeb2ac.png)

## 致谢

感谢以下开源项目提供的思路和能力支持：

- [r3x5ur/unveilr](https://github.com/r3x5ur/unveilr)
- [Ackites/KillWxapkg](https://github.com/Ackites/KillWxapkg)
- [x0tools/WeChatOpenDevTools](https://github.com/x0tools/WeChatOpenDevTools)
- [mrknow001/wx_sessionkey_decrypt](https://github.com/mrknow001/wx_sessionkey_decrypt)
- [JaveleyQAQ/WeChatOpenDevTools-Python](https://github.com/JaveleyQAQ/WeChatOpenDevTools-Python)
- [Spade-sec/First](https://github.com/Spade-sec/First)
