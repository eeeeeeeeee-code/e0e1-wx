var address = {
        "LaunchAppletBegin": "0x264AAED",
        "WechatAppHtml":"0x24C006B",
        "WechatWebHtml":"0x24C0064",
        "SetEnableDebug":"0x9A57860",
        "MenuItemDevToolsString":"0x287A485"
    }


//获取WeChatAppEx.exe的基址
var base = Process.findModuleByName("WeChatAppEx.exe").base
for(var addressname in address){
    address[addressname] = base.add(parseInt(address[addressname]));
}

function readStdString(s) {
    var flag = s.add(23).readU8()
    if (flag == 0x80) {
        var size = s.add(8).readUInt()
        return s.readPointer().readUtf8String(size)
    } else {
        return s.readUtf8String(flag)
    }
}

function writeStdString(s, content) {
    var flag = s.add(23).readU8()
    if (flag == 0x80) {
        // 从堆中写入
        var orisize = s.add(8).readUInt()
        if (content.length > orisize) {
            throw "must below orisize!"
        }
        s.readPointer().writeUtf8String(content)
        s.add(8).writeUInt(content.length)
    } else {
        // 从栈中写入
        if (content.length > 22) {
            throw "max 23 for stack str"
        }
        s.writeUtf8String(content)
        s.add(23).writeU8(content.length)
    }
}

//HOOK 启动配置
Interceptor.attach(address.LaunchAppletBegin, {
    onEnter(args) {
//        send("HOOK到小程序加载! " + readStdString(args[1]))
        for (var i = 0; i < 0x1000; i+=8) {
            try {
                var s = readStdString(args[2].add(i))
//                if(s.length>0){
////                    send(s)
//                }
                var s1 = s.replaceAll("md5", "md6").replaceAll('"enable_vconsole":false', '"enable_vconsole": true')
                if (s !== s1) {
                    //send("拦截到小程序加载")
                    writeStdString(args[2].add(i), s1)
                }
            } catch (a) {
            }
        }
    }
})

/* Interceptor.attach(address.test, {
    onEnter(args) {
        //this.context.rdx.writeU8(1)
        send("LOG1:" + args[2].readU8())
    }
}) */

//HOOK F12配置 替换原本内容
Interceptor.attach(address.WechatAppHtml, {
    onEnter(args) {
        this.context.rdx = address.WechatWebHtml;
    }
})

send("WeChatAppEx.exe 注入成功!")