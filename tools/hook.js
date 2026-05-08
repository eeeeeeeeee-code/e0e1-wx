const VERBOSE = false;
const PLATFORM = Process.platform;  // 'darwin' | 'windows'
const ARCH = Process.arch;          // 'arm64' | 'x64' | 'x86_64' | ...

// ── Module Resolution ──

const getMainModule = (version) => {
    if (PLATFORM === "darwin") {
        return Process.findModuleByName("WeChatAppEx Framework");
    }
    // Windows: flue.dll for newer versions
    if (version >= 13331) {
        return Process.findModuleByName("flue.dll");
    }
    return Process.findModuleByName("WeChatAppEx.exe");
};

// ── Scene Values ──

const SCENE_WHITELIST = [
    1005, 1007, 1008, 1012, 1027, 1035, 1053, 1074,
    1145, 1168, 1178, 1256, 1260, 1302, 1308,
];

// ── CDP Filter Patch (shared logic, platform-specific pointer access) ──

const patchCDPFilter = (base, offset) => {
    // xref: SendToClientFilter / devtools_message_filter_applet_webview.cc
    Interceptor.attach(base.add(offset), {
        onEnter(args) {
            if (PLATFORM === "windows") {
                this.inputValue = args[0];
            }
        },
        onLeave(retval) {
            let target;
            if (PLATFORM === "darwin") {
                // macOS: retval points directly to the struct
                if (!retval || retval.isNull()) return;
                target = retval.add(8);
            } else {
                // Windows: dereference args[0] to get the struct pointer
                const ptr = this.inputValue.readPointer();
                if (ptr.isNull() || ptr.add(8).isNull()) return;
                target = ptr.add(8);
            }
            VERBOSE && console.log(`[patch] CDP filter v8[2]: ${target.readU32()}`);
            if (target.readU32() === 6) {
                target.writeU32(0x0);
            }
        },
    });
};

// ── Resource Cache Policy Patch (darwin only) ──

const patchResourceCachePolicy = (base, offset) => {
    // xref: WAPCAdapterAppIndex.js
    Interceptor.attach(base.add(offset), {
        onLeave(retval) {
            VERBOSE && console.log(`[patch] cache policy retval: ${retval.toInt32()} -> 0`);
            retval.replace(0x0);
        },
    });
};

// ── OnLoadStart: Darwin ──

const darwinPatchLoadStart = (base, offset) => {
    // xref: AppletIndexContainer::OnLoadStart (first match)
    // Force debug mode by setting second param to true
    Interceptor.attach(base.add(offset), {
        onEnter() {
            console.log("[hook] AppletIndexContainer::OnLoadStart onEnter");
            if (ARCH === "arm64") {
                this.context.x1 = (this.context.x1 & ~0xff) | 0x1;
            } else {
                // x64 / x86_64: System V ABI, second param = RSI
                this.context.rsi = (this.context.rsi & ~0xff) | 0x1;
            }
        },
        onLeave() {},
    });
};

const darwinPatchLoadStart2 = (base, offset, structOffset) => {
    // xref: AppletIndexContainer::OnLoadStart (last function)
    // Hijack scene value via struct pointer chain
    Interceptor.attach(base.add(offset), {
        onEnter(args) {
            try {
                const v4 = args[0].add(8).readPointer();
                if (!v4 || v4.isNull()) return;
                const q1 = v4.add(structOffset).readPointer();
                if (!q1 || q1.isNull()) return;
                const q2 = q1.add(16).readPointer();
                if (!q2 || q2.isNull()) return;
                const scenePtr = q2.add(488);
                const scene = scenePtr.readInt();
                console.log(`[hook] scene: ${scene}`);
                if (SCENE_WHITELIST.includes(scene)) {
                    console.log("[hook] hook scene -> 1101");
                    scenePtr.writeInt(1101);
                }
            } catch (e) {
                console.error(`[hook] onLoadStart2 error: ${e}`);
            }
        },
        onLeave() {},
    });
};

// ── OnLoadStart: Windows ──

const winPatchLoadStart = (base, config) => {
    // xref: AppletIndexContainer::OnLoadStart
    // Windows combines debug flag + scene hijack in one hook
    Interceptor.attach(base.add(config.LoadStartHookOffset), {
        onEnter() {
            // Microsoft x64 ABI: second param = RDX, force debug mode
            if ((this.context.rdx & 0xff) !== 1) {
                this.context.rdx = (this.context.rdx & ~0xff) | 0x1;
            }
            // Scene hijack via SceneOffsets pointer chain
            try {
                const offsets = config.SceneOffsets;
                const ptr1 = this.context.rcx.add(56).readPointer().add(offsets[0]).readPointer();
                const scenePtr = ptr1.add(8).readPointer().add(offsets[1]).readPointer().add(16).readPointer().add(488);
                const scene = scenePtr.readInt();
                send(`[hook] scene: ${scene}`);
                if (SCENE_WHITELIST.includes(scene)) {
                    send("[hook] hook scene -> 1101");
                    scenePtr.writeInt(1101);
                }
            } catch (e) {
                send(`[hook] scene hook error: ${e}`);
            }
        },
        onLeave() {},
    });
};

// ── Config Parsing ──

const parseConfig = () => {
    const rawConfig = `@@CONFIG@@`;
    if (rawConfig.includes("@@")) {
        // Fallback test config
        if (PLATFORM === "darwin") {
            return {
                Version: 17078,
                Arch: {
                    arm64: {
                        LoadStartHookOffset: "0x4F0620C",
                        LoadStartHookOffset2: "0x81CEC08",
                        CDPFilterHookOffset: "0x81BFC04",
                        ResourceCachePolicyHookOffset: "0x4F699E8",
                        StructOffset: 1376,
                    },
                },
            };
        }
        return {
            Version: 18955,
            LoadStartHookOffset: "0x25B52C0",
            CDPFilterHookOffset: "0x30248B0",
            SceneOffsets: [1408, 1344, 488],
        };
    }
    return JSON.parse(rawConfig);
};

const resolveArchConfig = (config) => {
    // Windows configs have offsets at top level — return directly
    if (config && config.LoadStartHookOffset) {
        return config;
    }
    // Mac configs nest under Arch.{arm64|x64}
    const table = config?.Arch || config?.arch;
    if (!table) return null;

    const candidates = [ARCH];
    if (ARCH === "x86_64") candidates.push("x64");
    if (ARCH === "amd64") candidates.push("x64");

    for (const key of candidates) {
        const picked = table[key];
        if (picked && picked.LoadStartHookOffset) {
            return { ...picked, Version: config.Version, __arch: key };
        }
    }
    return null;
};

// ── Main ──

const main = () => {
    const rawConfig = parseConfig();
    const config = resolveArchConfig(rawConfig);

    if (!config) {
        console.error(`[frida] no config for platform=${PLATFORM} arch=${ARCH}`);
        return;
    }

    const mainModule = getMainModule(config.Version);
    if (!mainModule) {
        const expected = PLATFORM === "darwin" ? "WeChatAppEx Framework" : "flue.dll / WeChatAppEx.exe";
        console.error(`[frida] module not found: ${expected}`);
        return;
    }

    console.log(`[frida] version=${config.Version} platform=${PLATFORM} arch=${config.__arch || ARCH}`);
    console.log(`[frida] module base: ${mainModule.base}`);

    const base = mainModule.base;

    // CDP filter patch — both platforms
    patchCDPFilter(base, config.CDPFilterHookOffset);

    if (PLATFORM === "darwin") {
        darwinPatchLoadStart(base, config.LoadStartHookOffset);
        darwinPatchLoadStart2(base, config.LoadStartHookOffset2, config.StructOffset);
        if (config.ResourceCachePolicyHookOffset) {
            patchResourceCachePolicy(base, config.ResourceCachePolicyHookOffset);
        }
    } else {
        winPatchLoadStart(base, config);
    }
};

main();
