(function () {
  if (window.__routeNavigator) {
    return;
  }

  // 这些 wx API 都会改变小程序页面栈，防跳转需要统一拦截。
  var GUARDED_WX_METHODS = ["navigateTo", "redirectTo", "reLaunch", "switchTab", "navigateBack"];

  // 收集可用的小程序运行 frame，路由读取要求有页面上下文，守卫只要求有 wx 对象。
  function addCandidate(candidates, frame, requireRouteContext) {
    try {
      if (!frame || candidates.indexOf(frame) >= 0) {
        return;
      }
      if (!frame.wx) {
        return;
      }
      if (!requireRouteContext || frame.__wxConfig || frame.getCurrentPages) {
        candidates.push(frame);
      }
    } catch (error) {}
  }

  // 遍历当前窗口、子 frame 和父窗口 frame，避免守卫只绑定到单个上下文。
  function collectCandidateFrames(requireRouteContext) {
    var candidates = [];
    var visited = [];

    function visit(frame, depth) {
      try {
        if (!frame || visited.indexOf(frame) >= 0 || depth > 3) {
          return;
        }
        visited.push(frame);
        addCandidate(candidates, frame, requireRouteContext);
        if (frame.frames) {
          for (var index = 0; index < frame.frames.length; index += 1) {
            visit(frame.frames[index], depth + 1);
          }
        }
      } catch (error) {}
    }

    visit(window, 0);
    try {
      if (window.parent && window.parent !== window) {
        visit(window.parent, 0);
      }
    } catch (error) {}
    return candidates;
  }

  function frameScore(frame) {
    try {
      var score = 0;
      if (frame.wx) {
        score += 1;
      }
      if (frame.__wxConfig) {
        score += 2;
      }
      if (typeof frame.getCurrentPages === "function") {
        var pages = frame.getCurrentPages() || [];
        if (pages.length > 0) {
          score += 10;
        }
        if (currentRoute(frame)) {
          score += 5;
        }
      }
      return score;
    } catch (error) {
      return 0;
    }
  }

  function detectFrame() {
    var candidates = collectCandidateFrames(true);
    var bestFrame = null;
    var bestScore = 0;
    candidates.forEach(function (frame) {
      var score = frameScore(frame);
      if (score > bestScore) {
        bestScore = score;
        bestFrame = frame;
      }
    });
    if (bestFrame) {
      return bestFrame;
    }
    throw new Error("未检测到小程序运行环境");
  }

  function normalizeRoute(route) {
    return String(route || "").replace(/^\/+/, "");
  }

  function routeUrl(route) {
    return "/" + normalizeRoute(route);
  }

  function currentRoute(frame) {
    var pages = frame.getCurrentPages ? frame.getCurrentPages() : [];
    if (!pages.length) {
      return "";
    }
    var current = pages[pages.length - 1];
    return current.route || current.__route__ || "";
  }

  function configPages(frame) {
    var config = frame.__wxConfig || {};
    var pages = [];
    var seen = {};

    (config.pages || []).forEach(function (route) {
      var normalized = normalizeRoute(route);
      if (!seen[normalized]) {
        seen[normalized] = true;
        pages.push({ route: normalized, source: "main", isTabBar: false });
      }
    });

    (config.subPackages || config.subpackages || []).forEach(function (pkg) {
      (pkg.pages || []).forEach(function (route) {
        var fullRoute = normalizeRoute(pkg.root + "/" + route);
        if (!seen[fullRoute]) {
          seen[fullRoute] = true;
          pages.push({ route: fullRoute, source: String(pkg.root || ""), isTabBar: false });
        }
      });
    });

    var tabBarPages = ((config.tabBar || {}).list || []).map(function (item) {
      return normalizeRoute(item.pagePath);
    });

    pages.forEach(function (page) {
      page.isTabBar = tabBarPages.indexOf(page.route) >= 0;
    });

    return { pages: pages, tabBarPages: tabBarPages };
  }

  function runWxMethod(frame, method, payload) {
    // 工具主动跳转时调用原始 wx 方法，避免被防跳转守卫反向拦截。
    var state = guardState();
    if (state.enabled) {
      patchGuardFrames(state, frame);
    }
    var wxMethod = originalWxMethod(frame, method, state);
    return new Promise(function (resolve) {
      if (typeof wxMethod !== "function") {
        resolve({ ok: false, action: method, currentRoute: currentRoute(frame), error: "wx." + method + " 不可用" });
        return;
      }
      try {
        wxMethod.call(frame.wx, {
          url: payload.route ? routeUrl(payload.route) : undefined,
          delta: payload.delta,
          success: function () {
            resolve({ ok: true, action: method, currentRoute: currentRoute(frame) });
          },
          fail: function (error) {
            resolve({
              ok: false,
              action: method,
              currentRoute: currentRoute(frame),
              error: (error && error.errMsg) || String(error || "unknown error"),
            });
          },
        });
      } catch (error) {
        resolve({ ok: false, action: method, currentRoute: currentRoute(frame), error: String(error || "unknown error") });
      }
    });
  }

  function guardState() {
    // 守卫状态挂在注入窗口上，跨 frame 共享拦截计数和原始方法表。
    if (!window.__routeGuardState) {
      window.__routeGuardState = {
        enabled: false,
        blocked: [],
        originals: [],
      };
    }
    if (!Array.isArray(window.__routeGuardState.originals)) {
      window.__routeGuardState.originals = [];
    }
    return window.__routeGuardState;
  }

  function guardEntryForFrame(state, frame, create) {
    // 为每个 frame 单独保存原始 wx 方法，关闭防跳转时按 frame 恢复。
    var originals = state.originals || [];
    for (var index = 0; index < originals.length; index += 1) {
      if (originals[index].frame === frame) {
        return originals[index];
      }
    }
    if (!create) {
      return null;
    }
    var entry = { frame: frame, methods: {} };
    originals.push(entry);
    state.originals = originals;
    return entry;
  }

  function originalWxMethod(frame, method, state) {
    // 优先取守卫启用前保存的原始方法；未启用守卫时直接使用当前 wx 方法。
    var entry = guardEntryForFrame(state || guardState(), frame, false);
    if (entry && typeof entry.methods[method] === "function") {
      return entry.methods[method];
    }
    return frame && frame.wx ? frame.wx[method] : null;
  }

  function guardedOk(method, frame, state, options) {
    // 模拟成功回调但不调用原始跳转方法，让业务侧认为调用已完成。
    var url = (options && options.url) || "";
    state.blocked.push({
      type: method,
      url: url,
      time: new Date().toLocaleTimeString(),
    });
    if (options && typeof options.success === "function") {
      options.success({ errMsg: method + ":ok" });
    }
    if (options && typeof options.complete === "function") {
      options.complete({ errMsg: method + ":ok" });
    }
    return { ok: true, enabled: true, currentRoute: currentRoute(frame) };
  }

  function makeGuardedMethod(method, frame, state) {
    // 生成带标记的包装函数，重复开启防跳转时不会把包装函数保存成原始方法。
    var wrapped = function (options) {
      return guardedOk(method, frame, state, options);
    };
    wrapped.__routeGuardWrapped = true;
    wrapped.__routeGuardMethod = method;
    return wrapped;
  }

  function patchFrameGuard(state, frame) {
    // 对单个 frame 的 wx 路由方法安装守卫。
    if (!frame || !frame.wx) {
      return;
    }
    var entry = guardEntryForFrame(state, frame, true);
    GUARDED_WX_METHODS.forEach(function (method) {
      var current = frame.wx[method];
      if (typeof current !== "function") {
        return;
      }
      if (current.__routeGuardWrapped && current.__routeGuardMethod === method) {
        return;
      }
      if (typeof entry.methods[method] !== "function") {
        entry.methods[method] = current;
      }
      frame.wx[method] = makeGuardedMethod(method, frame, state);
    });
  }

  function patchGuardFrames(state, preferredFrame) {
    // 对全部候选 frame 安装守卫，并补上当前检测到的首选 frame。
    var frames = collectCandidateFrames(false);
    addCandidate(frames, preferredFrame, false);
    frames.forEach(function (frame) {
      patchFrameGuard(state, frame);
    });
  }

  function restoreGuardFrames(state) {
    // 关闭防跳转时恢复所有 frame 的原始 wx 方法。
    (state.originals || []).forEach(function (entry) {
      if (!entry || !entry.frame || !entry.frame.wx || !entry.methods) {
        return;
      }
      Object.keys(entry.methods).forEach(function (method) {
        if (typeof entry.methods[method] === "function") {
          entry.frame.wx[method] = entry.methods[method];
        }
      });
    });
  }

  function enableRedirectGuard(frame) {
    // 开启防跳转时清空旧拦截计数，并允许重复调用补齐新出现的 frame。
    var state = guardState();
    var already = !!state.enabled;
    if (!already) {
      state.enabled = true;
      state.blocked = [];
      state.originals = [];
    }
    patchGuardFrames(state, frame);
    return { ok: true, enabled: true, already: already };
  }

  function disableRedirectGuard(frame) {
    // 关闭防跳转后不再保留原始方法引用，避免后续页面上下文泄漏。
    var state = guardState();
    if (!state.enabled) {
      return { ok: true, enabled: false };
    }
    restoreGuardFrames(state);
    state.enabled = false;
    state.originals = [];
    return { ok: true, enabled: false };
  }

  function currentGuardSnapshot(frame) {
    // 读取状态时也补齐守卫，覆盖页面跳转后新增的 frame。
    var state = guardState();
    if (state.enabled) {
      patchGuardFrames(state, frame);
    }
    return {
      guardEnabled: !!state.enabled,
      blockedRedirectsCount: (state.blocked || []).length,
    };
  }

  window.__routeNavigator = {
    fetchConfigJson: function () {
      var frame = detectFrame();
      var config = configPages(frame);
      var guard = currentGuardSnapshot(frame);
      return JSON.stringify({
        pages: config.pages,
        tabBarPages: config.tabBarPages,
        currentRoute: currentRoute(frame),
        guardEnabled: guard.guardEnabled,
        blockedRedirectsCount: guard.blockedRedirectsCount,
      });
    },
    navigateToJson: function (route) {
      return runWxMethod(detectFrame(), "navigateTo", { route: route }).then(JSON.stringify);
    },
    switchTabJson: function (route) {
      return runWxMethod(detectFrame(), "switchTab", { route: route }).then(JSON.stringify);
    },
    redirectToJson: function (route) {
      return runWxMethod(detectFrame(), "redirectTo", { route: route }).then(JSON.stringify);
    },
    reLaunchJson: function (route) {
      return runWxMethod(detectFrame(), "reLaunch", { route: route }).then(JSON.stringify);
    },
    navigateBackJson: function (_route, delta) {
      return runWxMethod(detectFrame(), "navigateBack", { delta: delta || 1 }).then(JSON.stringify);
    },
    enableRedirectGuardJson: function () {
      return Promise.resolve(JSON.stringify(enableRedirectGuard(detectFrame())));
    },
    disableRedirectGuardJson: function () {
      return Promise.resolve(JSON.stringify(disableRedirectGuard(detectFrame())));
    },
  };
})();
