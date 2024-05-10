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

### 效果展示

![mnggiflab-compressed-lqy83-miqwy (1)-min](https://github.com/eeeeeeeeee-code/e0e1-wx/assets/115862499/24a56b9f-29fb-4fee-9112-fdd125824f0d)

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

> 来到https://github.com/x0tools/WeChatOpenDevTools/tree/main/Core/WeChatAppEx.exe，查看对应版本的addres

![image](https://github.com/eeeeeeeeee-code/e0e1-wx/assets/115862499/b0f5efd0-36e4-4f2d-8e48-4ccbe418d98b)

> 来到脚本./tools/WeChatAppEx.exe.js文件中，修改addres参数为对应的版本addres

![image](https://github.com/eeeeeeeeee-code/e0e1-wx/assets/115862499/12dfb004-6bcb-4935-a3c8-99992efb9107)



### 使用方法

```
# 不进行hook
python3 e0e1-wx.py

# 进行hook
python3 e0e1-wx.py --hook
```


### 致谢

> 反编译工具使用的是，免费版本的 https://github.com/r3x5ur/unveilr
>
> 基址和hook使用的是 https://github.com/x0tools/WeChatOpenDevTools
>
> 感谢大佬们的工具
