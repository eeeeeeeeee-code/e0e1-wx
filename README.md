# e0e1-wx

### 简介

> 1. 还在一个个反编译小程序吗？
> 2. 还在自己一个个注入hook吗？
> 3. 还在一个个查看找接口、查找泄露吗？
>
> 现在有自动化辅助渗透脚本了，自动化辅助反编译、自动化注入hook、自动化查看泄露
>
> 注：本工具仅用于学习参考，任何事情与作者无关

> 平台限制：windows



### 版本更新
> 2025-4-25  版本：2.0
>
> 1. 去除外部工具调用，所有功能本地化实现方便后续添加功能 (如：hook 云函数之类的)
> 2. 去除请求功能（作用不大）
> 3. 添加微信 sessionkey、iv解密加密功能，可能一些小程序还在用，遇到可能就是任意用户的登录了
> 
> 2024-11-28  版本：1.22
> 
>  1. 修复bug，releases下载1.21版本替换成 1.21版本的e0e1-wx.py
>
> 2024-8-27  版本：1.21 先放置到releases中，项目上传不上去
> 
>  1. 更新了反编译工具，同时添加了代码优化功能
>  2. 针对误报问题，更新正则并移至config.yaml中，可以自行更改添加
> 


### 效果展示

![mnggiflab-compressed-lqy83-miqwy (1)-min](https://github.com/eeeeeeeeee-code/e0e1-wx/assets/115862499/24a56b9f-29fb-4fee-9112-fdd125824f0d)


### 功能优化
> 查看https://github.com/eeeeeeeeee-code/wx-hook
>
> 1. 解决高版本没有偏移码无法hook的问题
>
> 2. 解决部分同志不会抓小程序包的问题
>

### 赞赏码
开源维护不易，有钱的大哥，可以请我喝一杯咖啡努努力ᕙ(• ॒ ູ•)ᕘ
![image](https://github.com/user-attachments/assets/fa9176a9-5247-4d0c-bd09-82f40125589e)

### config.yaml文件解释

```
tools:
  proess_file: "proess.xlsx"
  # 最大线程数
  max_workers: 5

wx-tools:
  # 微信位置(必须配置)，注意这里必须使用的是单引号
  wx-file: ''
  
# 配置正则处，前面是正则名字 后面为正则匹配条件，可自行更改添加
rekey:
  google_api: 'AIza[0-9A-Za-z-_]{35}'
  firebase: 'AAAA[A-Za-z0-9_-]{7}:[A-Za-z0-9_-]{140}'
  google_captcha: '6L[0-9A-Za-z-_]{38}|^6[0-9a-zA-Z_-]{39}$'
  ......
```



### config配置

1.配置wx文件夹位置配置

来到设置，查看文件管理对应的文件夹位置

![image](https://github.com/eeeeeeeeee-code/e0e1-wx/assets/115862499/0430a112-22bf-4071-8ffe-01d595d62f93)

![image](https://github.com/eeeeeeeeee-code/e0e1-wx/assets/115862499/191392dc-c79c-43d9-acd3-86285a1df5fe)

![image](https://github.com/eeeeeeeeee-code/e0e1-wx/assets/115862499/abc71f6d-5667-41df-9d24-4d855b175018)

2.配置hook，如果想进行hook-f12，我们需要配置对应的基址

> 首先查看 %appdata%\Tencent\WeChat\XPlugin\Plugins\RadiumWMPF\ 文件夹
>
> 如果这里有两个，就是版本新的，修改日期新的的这个，如果不行就回头试试另一个，这里记住对应的版本

![image](https://github.com/eeeeeeeeee-code/e0e1-wx/assets/115862499/5d96cf56-36be-4c1a-b05a-43efd0a07a86)

> 来到https://github.com/x0tools/WeChatOpenDevTools/tree/main/Core/WeChatAppEx.exe  ，查看对应版本的addres
>
> 或者到 https://github.com/eeeeeeeeee-code/wx-hook/tree/master/addres  查看对应的基址

![image](https://github.com/eeeeeeeeee-code/e0e1-wx/assets/115862499/b0f5efd0-36e4-4f2d-8e48-4ccbe418d98b)

> 来到脚本./tools/WeChatAppEx.exe.js文件中，修改addres参数为对应的版本addres

![image](https://github.com/eeeeeeeeee-code/e0e1-wx/assets/115862499/12dfb004-6bcb-4935-a3c8-99992efb9107)



### 使用方法

```
# 不进行hook，还原项目结构
python3 e0e1-wx.py -r

# 进行hook
python3 e0e1-wx.py -hook

# 进行hook同时对输出的代码进行优化，同时还原项目结构
python3 .\e0e1-wx.py -hook -p -r
```



### 致谢

https://github.com/r3x5ur/unveilr

https://github.com/Ackites/KillWxapkg

https://github.com/x0tools/WeChatOpenDevTools

https://github.com/mrknow001/wx_sessionkey_decrypt
