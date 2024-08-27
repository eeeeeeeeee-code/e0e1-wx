# e0e1-wx

### 简介

> 1.还在一个个反编译小程序吗？
>
> 2.还在自己一个个注入hook吗？
>
> 3.还在一个个查看找接口、查找泄露吗？
>
> 现在有自动化辅助渗透脚本了，自动化辅助反编译、自动化注入hook、自动化查看泄露
>
> 注：本工具仅用于学习参考，任何事情与作者无关

> 平台限制：windows



### 版本更新

> 2024-8-27  版本：1.21
> 
> 1.更新了反编译工具，同时添加了代码优化功能
> 
> 2.针对误报问题，更新正则并移至config.yaml中，可以自行更改添加
> 



### 效果展示

![mnggiflab-compressed-lqy83-miqwy (1)-min](https://github.com/eeeeeeeeee-code/e0e1-wx/assets/115862499/24a56b9f-29fb-4fee-9112-fdd125824f0d)



### config.yaml文件解释

```
tools:
  # 是否开启请求接口
  asyncio_http_tf: False
  # 小程序结果保存的文件名
  proess_file: "proess.xlsx"
  # 不进行拼接的接口的url,不写入该状态码的接口
  not_asyncio_http: ["weixin.qq.com", "www.w3.org", "map.qq.com", "restapi.amap.com"]
  not_asyncio_stats: [404]
  # 最大线程数
  max_workers: 5
  # 工具运行时间限制，单位秒
  wxpcmd_timeout: 30

wx-tools:
  # 微信位置(必须配置)，注意这里必须使用的是单引号
  wx-file: ''

bot:
  # 飞书机器人配置，是否开启飞书提醒
  feishu-tf: False
  api_id: ""
  api_secret: ""
  phone: [""]
  
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
# 不进行hook
python3 e0e1-wx.py

# 进行hook
python3 e0e1-wx.py -hook

# 进行hook同时对输出的代码进行优化
python3 .\e0e1-wx.py -hook -pretty
```



### 致谢

> 反编译工具使用的是，免费版本的 https://github.com/r3x5ur/unveilr
>
> 新版使用为https://github.com/Ackites/KillWxapkg
>
> 基址和hook使用的是 https://github.com/x0tools/WeChatOpenDevTools
>
> 感谢大佬们的工具

![0482e1b53827cb22e5407b3608551c6](https://github.com/eeeeeeeeee-code/e0e1-wx/assets/115862499/949d3706-4425-46e6-9f92-f86043689810)
