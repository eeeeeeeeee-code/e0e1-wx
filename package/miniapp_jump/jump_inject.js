(function () {
  if (window.__miniappJumpNavigator) {
    return;
  }

  var TAP_EVENT_TYPES = ["tap", "longtap", "longpress"];
  var RESERVED_METHOD_NAMES = {
    constructor: true,
    onLoad: true,
    onReady: true,
    onShow: true,
    onHide: true,
    onUnload: true,
    onPullDownRefresh: true,
    onReachBottom: true,
    onShareAppMessage: true,
    onPageScroll: true,
    onResize: true,
    onTabItemTap: true,
    setData: true,
    selectComponent: true,
    selectAllComponents: true,
    createSelectorQuery: true,
    getTabBar: true,
    getPageId: true,
  };

  function buildResult(appId, path, ok, status, message, error) {
    return {
      ok: !!ok,
      status: String(status || (ok ? "success" : "failed")),
      action: "navigate_to_mini_program",
      appId: String(appId || ""),
      path: normalizePath(path),
      message: String(message || ""),
      error: String(error || ""),
    };
  }

  function normalizeAppId(appId) {
    return String(appId || "").trim();
  }

  function normalizePath(path) {
    return String(path || "").trim().replace(/^\/+/, "");
  }

  function uniquePush(items, value) {
    for (var index = 0; index < items.length; index += 1) {
      if (items[index] === value) {
        return;
      }
    }
    items.push(value);
  }

  function addCandidate(candidates, frame) {
    try {
      if (!frame || candidates.indexOf(frame) >= 0) {
        return;
      }
      if (!frame.wx || typeof frame.wx.navigateToMiniProgram !== "function") {
        return;
      }
      if (!frame.__wxConfig && typeof frame.getCurrentPages !== "function") {
        return;
      }
      candidates.push(frame);
    } catch (error) {}
  }

  function collectCandidateFrames() {
    var candidates = [];
    var visited = [];

    function visit(frame, depth) {
      try {
        if (!frame || visited.indexOf(frame) >= 0 || depth > 3) {
          return;
        }
        visited.push(frame);
        addCandidate(candidates, frame);
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

  function currentRoute(frame) {
    try {
      var pages = typeof frame.getCurrentPages === "function" ? frame.getCurrentPages() || [] : [];
      if (!pages.length) {
        return "";
      }
      var current = pages[pages.length - 1];
      return String(current.route || current.__route__ || "");
    } catch (error) {
      return "";
    }
  }

  function frameScore(frame) {
    try {
      var score = 0;
      if (frame.wx && typeof frame.wx.navigateToMiniProgram === "function") {
        score += 2;
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
    var candidates = collectCandidateFrames();
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
    throw new Error("未检测到可用的小程序运行环境");
  }

  function currentPage(frame) {
    try {
      var pages = typeof frame.getCurrentPages === "function" ? frame.getCurrentPages() || [] : [];
      if (!pages.length) {
        return null;
      }
      return pages[pages.length - 1];
    } catch (error) {
      return null;
    }
  }

  function textOfError(error) {
    if (!error) {
      return "";
    }
    if (typeof error === "string") {
      return error;
    }
    return String(error.errMsg || error.message || error);
  }

  function failureMessage(errorText) {
    var text = String(errorText || "");
    if (!text) {
      return "小程序跳转失败";
    }
    if (text.indexOf("invalid appid") >= 0) {
      return "AppID 无效或小程序不存在";
    }
    if (text.indexOf("not released") >= 0) {
      return "目标小程序未发布";
    }
    if (text.indexOf("not found") >= 0 || text.indexOf("path") >= 0) {
      return "页面路径错误";
    }
    if (text.indexOf("cancel") >= 0) {
      return "用户取消跳转";
    }
    if (text.indexOf("can only be invoked by user TAP gesture") >= 0) {
      return "当前点击未进入原生 TAP 回调，请再次点击小程序内已有控件";
    }
    return "小程序跳转失败";
  }

  function callNavigateToMiniProgram(frame, appId, path) {
    return new Promise(function (resolve) {
      try {
        if (!frame || !frame.wx || typeof frame.wx.navigateToMiniProgram !== "function") {
          resolve(
            buildResult(
              appId,
              path,
              false,
              "failed",
              "wx.navigateToMiniProgram 不可用",
              "wx.navigateToMiniProgram not available"
            )
          );
          return;
        }
        var normalizedPath = normalizePath(path);
        var options = {
          appId: appId,
          envVersion: "release",
          success: function () {
            resolve(buildResult(appId, normalizedPath, true, "success", "小程序跳转完成", ""));
          },
          fail: function (error) {
            var errorText = textOfError(error);
            var cancelled = errorText.indexOf("cancel") >= 0;
            resolve(
              buildResult(
                appId,
                normalizedPath,
                false,
                cancelled ? "cancelled" : "failed",
                failureMessage(errorText),
                errorText
              )
            );
          },
        };
        if (normalizedPath) {
          options.path = normalizedPath;
        }
        frame.wx.navigateToMiniProgram(options);
      } catch (error) {
        var errorText = textOfError(error);
        resolve(buildResult(appId, path, false, "failed", failureMessage(errorText), errorText));
      }
    });
  }

  function shouldSkipMethod(name) {
    return !!RESERVED_METHOD_NAMES[String(name || "")];
  }

  function isTapEvent(event) {
    if (!event || typeof event !== "object") {
      return false;
    }
    var eventType = String(event.type || "").toLowerCase();
    return TAP_EVENT_TYPES.indexOf(eventType) >= 0;
  }

  function collectHookTargets(page) {
    var targets = [];
    var seen = {};

    function addOwner(owner, keySource) {
      if (!owner || (typeof owner !== "object" && typeof owner !== "function")) {
        return;
      }
      var keys = [];
      try {
        keys = keySource === "prototype" ? Object.getOwnPropertyNames(owner) : Object.keys(owner);
      } catch (error) {
        keys = [];
      }
      keys.forEach(function (key) {
        var methodName = String(key || "");
        if (!methodName || shouldSkipMethod(methodName)) {
          return;
        }
        var dedupeKey = keySource + ":" + methodName;
        if (seen[dedupeKey]) {
          return;
        }
        var value = null;
        try {
          value = owner[methodName];
        } catch (error) {
          value = null;
        }
        if (typeof value !== "function") {
          return;
        }
        seen[dedupeKey] = true;
        targets.push({
          owner: owner,
          key: methodName,
          original: value,
        });
      });
    }

    addOwner(page, "own");
    try {
      var prototype = Object.getPrototypeOf(page);
      if (prototype && prototype !== Object.prototype) {
        addOwner(prototype, "prototype");
      }
    } catch (error) {}
    return targets;
  }

  function restorePendingTapHook() {
    var navigatorState = window.__miniappJumpNavigator;
    var pending = navigatorState && navigatorState._pending;
    if (!pending || !Array.isArray(pending.hooks)) {
      navigatorState._pending = null;
      return;
    }
    pending.hooks.forEach(function (entry) {
      try {
        if (entry && entry.owner && entry.key && entry.owner[entry.key] === entry.wrapped) {
          entry.owner[entry.key] = entry.original;
        }
      } catch (error) {}
    });
    navigatorState._pending = null;
  }

  function installPendingTapHook(frame, appId, path) {
    restorePendingTapHook();
    var page = currentPage(frame);
    if (!page) {
      throw new Error("未检测到当前小程序页面");
    }
    var targets = collectHookTargets(page);
    if (!targets.length) {
      throw new Error("当前页面未检测到可接管的点击处理函数");
    }

    var pending = {
      appId: appId,
      path: normalizePath(path),
      frame: frame,
      route: currentRoute(frame),
      handled: false,
      hooks: [],
    };
    window.__miniappJumpNavigator._pending = pending;

    targets.forEach(function (target) {
      var original = target.original;
      var wrapped = function () {
        var args = Array.prototype.slice.call(arguments);
        if (
          !pending.handled &&
          window.__miniappJumpNavigator._pending === pending &&
          isTapEvent(args[0])
        ) {
          pending.handled = true;
          restorePendingTapHook();
          window.__miniappJumpNavigator._state = buildResult(
            appId,
            pending.path,
            false,
            "executing",
            "检测到原生 TAP，正在跳转小程序",
            ""
          );
          callNavigateToMiniProgram(frame, appId, pending.path).then(function (result) {
            window.__miniappJumpNavigator._state = result;
          });
          return;
        }
        return original.apply(this, args);
      };
      try {
        target.owner[target.key] = wrapped;
        pending.hooks.push({
          owner: target.owner,
          key: target.key,
          original: original,
          wrapped: wrapped,
        });
      } catch (error) {}
    });

    if (!pending.hooks.length) {
      restorePendingTapHook();
      throw new Error("当前页面点击处理函数不可写，无法接管原生 TAP");
    }
    return pending.hooks.length;
  }

  function prepareNavigateToMiniProgram(appId, path) {
    var normalizedAppId = normalizeAppId(appId);
    var normalizedPath = normalizePath(path);
    if (!normalizedAppId) {
      return buildResult("", normalizedPath, false, "failed", "目标 AppID 不能为空", "appid is empty");
    }
    try {
      var frame = detectFrame();
      var hookCount = installPendingTapHook(frame, normalizedAppId, normalizedPath);
      var route = currentRoute(frame);
      var message = "请在小程序内点击任意已有可点击控件完成跳转";
      if (route) {
        message += "（当前页面：" + route + "，已接管 " + String(hookCount) + " 个点击处理函数）";
      }
      return buildResult(normalizedAppId, normalizedPath, false, "waiting_tap", message, "");
    } catch (error) {
      var errorText = textOfError(error);
      return buildResult(normalizedAppId, normalizedPath, false, "failed", "小程序跳转准备失败", errorText);
    }
  }

  function currentState() {
    var state = window.__miniappJumpNavigator._state;
    if (state && typeof state === "object") {
      return state;
    }
    return buildResult("", "", false, "failed", "未找到待处理跳转任务", "no pending navigation");
  }

  window.__miniappJumpNavigator = {
    _pending: null,
    _state: null,

    prepareNavigateToMiniProgramJson: function (appId, path) {
      var result = prepareNavigateToMiniProgram(appId, path);
      window.__miniappJumpNavigator._state = result;
      return Promise.resolve(JSON.stringify(result));
    },

    pollNavigationResultJson: function () {
      return Promise.resolve(JSON.stringify(currentState()));
    },

    cancelPendingNavigationJson: function () {
      var current = currentState();
      restorePendingTapHook();
      var result = buildResult(current.appId, current.path, false, "cancelled", "小程序跳转任务已取消", "");
      window.__miniappJumpNavigator._state = result;
      return Promise.resolve(JSON.stringify(result));
    },

    navigateToMiniProgramJson: function (appId, path) {
      return this.prepareNavigateToMiniProgramJson(appId, path);
    },
  };
})();
