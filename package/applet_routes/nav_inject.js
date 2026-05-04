(function () {
  if (window.__routeNavigator) {
    return;
  }

  function detectFrame() {
    if (typeof wx !== "undefined" && typeof getCurrentPages !== "undefined") {
      return window;
    }
    if (window.frames) {
      for (var index = 0; index < window.frames.length; index += 1) {
        try {
          if (window.frames[index].wx && window.frames[index].__wxConfig) {
            return window.frames[index];
          }
        } catch (error) {}
      }
    }
    if (window.parent && window.parent.frames) {
      for (var parentIndex = 0; parentIndex < window.parent.frames.length; parentIndex += 1) {
        try {
          if (window.parent.frames[parentIndex].wx && window.parent.frames[parentIndex].__wxConfig) {
            return window.parent.frames[parentIndex];
          }
        } catch (error) {}
      }
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
    return new Promise(function (resolve) {
      frame.wx[method]({
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
    });
  }

  function guardState(frame) {
    if (!window.__routeGuardState) {
      window.__routeGuardState = {
        frame: frame,
        enabled: false,
        blocked: [],
        originals: {},
      };
    }
    if (window.__routeGuardState.frame !== frame) {
      window.__routeGuardState.frame = frame;
      window.__routeGuardState.enabled = false;
      window.__routeGuardState.blocked = [];
      window.__routeGuardState.originals = {};
    }
    return window.__routeGuardState;
  }

  function guardedOk(method, frame, state, options) {
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

  function enableRedirectGuard(frame) {
    var state = guardState(frame);
    if (state.enabled) {
      return { ok: true, enabled: true, already: true };
    }
    state.enabled = true;
    state.blocked = [];
    state.originals = {
      navigateTo: frame.wx.navigateTo,
      redirectTo: frame.wx.redirectTo,
      reLaunch: frame.wx.reLaunch,
    };

    frame.wx.navigateTo = function (options) {
      guardedOk("navigateTo", frame, state, options);
    };
    frame.wx.redirectTo = function (options) {
      guardedOk("redirectTo", frame, state, options);
    };
    frame.wx.reLaunch = function (options) {
      guardedOk("reLaunch", frame, state, options);
    };
    return { ok: true, enabled: true };
  }

  function disableRedirectGuard(frame) {
    var state = guardState(frame);
    if (!state.enabled) {
      return { ok: true, enabled: false };
    }
    if (state.originals.navigateTo) {
      frame.wx.navigateTo = state.originals.navigateTo;
    }
    if (state.originals.redirectTo) {
      frame.wx.redirectTo = state.originals.redirectTo;
    }
    if (state.originals.reLaunch) {
      frame.wx.reLaunch = state.originals.reLaunch;
    }
    state.enabled = false;
    state.originals = {};
    return { ok: true, enabled: false };
  }

  function currentGuardSnapshot(frame) {
    var state = guardState(frame);
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
