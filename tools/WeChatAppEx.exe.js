

var address = {
  "LaunchAppletBegin": "0x264A9E2",
  "MenuItemDevToolsString":"0x265A33A",
  "SwitchVersion":"0x24C0074",
  "Version":9129
}

// 获取 WeChatAppEx.exe 的基址，支持多个可能的模块名
var module = Process.findModuleByName("WeChatAppEx.exe") || Process.findModuleByName('WeChatAppEx Framework')
if (!module) {
    throw new Error("未找到 WeChatAppEx 模块！");
}
var base = module.base;

// 转换地址偏移为绝对地址（自动过滤空键名和 null 值）
Object.keys(address).forEach(key => {
    if (key && key !== "Version" && address[key] !== null && address[key] !== undefined) {
        address[key] = base.add(address[key]);
    }
});

send("[+] WeChatAppEx 注入成功!");

function readStdString(s) {
    var flag = s.add(23).readU8()
    if (flag == 0x80) {
        var size = s.add(8).readUInt()
        return s.readPointer().readUtf8String(size)
    } else {
        return s.readUtf8String(flag)
    }
}

// 写入 std::string 对象
function writeStdString(s, content) {
    var flag = s.add(23).readU8()
    if (flag == 0x80) {
        var orisize = s.add(8).readUInt()
        if (content.length > orisize) {
            throw new Error("内容长度超过原始大小");
        }
        s.readPointer().writeUtf8String(content)
        s.add(8).writeUInt(content.length)
    } else {
        if (content.length > 22) {
            throw new Error("栈字符串最大22字节");
        }
        s.writeUtf8String(content)
        s.add(23).writeU8(content.length)
    }
}

// 发送消息
function sendMessage(msg) {
    if (msg !== null && msg !== undefined) {
        send(msg);
    }
}

// ============================================
// 核心 Hook 功能
// ============================================

function hookLaunchParams() {
    if (!address.LaunchAppletBegin) return;

    Interceptor.attach(address.LaunchAppletBegin, {
        onEnter(args) {
            try {
                var appId = readStdString(args[1]);

                for (var i = 0; i < 0x1000; i += 8) {
                    try {
                        var s = readStdString(args[2].add(i))
                        var s1 = s
                            .replaceAll('"enable_vconsole":false', '"enable_vconsole":true')
                            .replaceAll("md5", "md6");

                        if (s !== s1) {
                            writeStdString(args[2].add(i), s1)
                        }
                    } catch (e) {}
                }
            } catch (e) {
                send("[!] hookLaunchParams 错误: " + e.message);
            }
        }
    })
}

// 设置版本特定的拦截器
function setupVersionSpecificInterceptor() {
    var hasOldMethod = address.WechatAppHtml && address.WechatWebHtml;
    var hasNewMethod = address.SwitchVersion;

    if (!hasOldMethod && !hasNewMethod) {
        send("[!] 缺少拦截器地址配置，跳过");
        return;
    }

    if (!address.Version) {
        // 没有指定版本，使用旧方法（如果有配置）
        if (hasOldMethod) {
            Interceptor.attach(address.WechatAppHtml, {
                onEnter(args) {
                    this.context.rdx = address.WechatWebHtml;
                    sendMessage();
                }
            });
        }
        return;
    }

    try {
        switch (address.Version) {
            case 8555:
                if (hasOldMethod) {
                    Interceptor.attach(address.WechatAppHtml, {
                        onEnter(args) {
                            this.context.rdx = address.WechatWebHtml;
                            sendMessage();
                        }
                    });
                }
                break;

            case 9079:
            case 9105:
            case 9115:
            case 9129:
            case 9193:
            case 11159:
            case 11205:
            case 11253:
            case 11275:
                // 新版本优先使用 SwitchVersion 方法
                if (hasNewMethod) {
                    Interceptor.attach(address.SwitchVersion, {
                        onEnter(args) {
                            this.context.r8 = this.context.rax;
                            sendMessage();
                        }
                    });
                } else if (hasOldMethod) {
                    // 回退到旧方法
                    Interceptor.attach(address.WechatAppHtml, {
                        onEnter(args) {
                            this.context.rdx = address.WechatWebHtml;
                            sendMessage();
                        }
                    });
                }
                break;

            default:
                // 未知版本，尝试旧方法
                if (hasOldMethod) {
                    Interceptor.attach(address.WechatAppHtml, {
                        onEnter(args) {
                            this.context.rdx = address.WechatWebHtml;
                            sendMessage();
                        }
                    });
                } else if (hasNewMethod) {
                    // 或者尝试新方法
                    Interceptor.attach(address.SwitchVersion, {
                        onEnter(args) {
                            this.context.r8 = this.context.rax;
                            sendMessage();
                        }
                    });
                }
                break;
        }
    } catch (e) {
        send("[!] setupInterceptor 错误: " + e.message);
    }
}

// 绕过 DevTools 检测
function bypassDevToolsDetection() {
    if (!address.MenuItemDevToolsString) return;

    try {
        var cr = new Uint8Array(address.MenuItemDevToolsString.readByteArray(7));
        var offset = (cr[3] & 0xFF) | ((cr[4] & 0xFF) << 8) |
                     ((cr[5] & 0xFF) << 16) | ((cr[6] & 0xFF) << 24);
        var ptr = address.MenuItemDevToolsString.add(offset + 7);

        Memory.protect(ptr, 8, 'rw-');
        ptr.writeUtf8String("DevTools");
    } catch (e) {
        send("[!] bypassDevTools 错误: " + e.message);
    }
}

try {
    bypassDevToolsDetection();
    hookLaunchParams();
    setupVersionSpecificInterceptor();
} catch (e) {
    send("[!] 初始化错误: " + e.message);
}
