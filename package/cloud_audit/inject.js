(function () {
  if (window._cloudAuditInjected) {
    return;
  }
  window._cloudAuditInjected = true;

  var cloudAudit = {
    hookedCalls: [],
    _hookedClouds: [],
    _autoHookTimer: null,
    _hooked: false,

    // 扫描当前上下文以及可访问 frame 中的 wx.cloud 实例。
    _findFrames: function () {
      var frames = [];
      var visited = [];

      function tryPush(target) {
        try {
          if (!target || !target.wx || !target.__wxConfig) {
            return;
          }
          for (var index = 0; index < visited.length; index += 1) {
            if (visited[index] === target) {
              return;
            }
          }
          visited.push(target);
          frames.push(target);
        } catch (error) {}
      }

      tryPush(window);
      try {
        if (window.parent && window.parent !== window) {
          tryPush(window.parent);
        }
      } catch (error) {}
      try {
        for (var frameIndex = 0; frameIndex < window.frames.length; frameIndex += 1) {
          tryPush(window.frames[frameIndex]);
        }
      } catch (error) {}
      return frames;
    },

    // 从 frame 运行时配置中获取 appId。
    _appIdFromFrame: function (frame) {
      try {
        if (frame.__wxConfig && frame.__wxConfig.accountInfo && frame.__wxConfig.accountInfo.appId) {
          return frame.__wxConfig.accountInfo.appId;
        }
        if (frame.__wxConfig && frame.__wxConfig.appId) {
          return frame.__wxConfig.appId;
        }
      } catch (error) {}
      return "";
    },

    // 通过 JSON 克隆数据，避免保留运行时对象引用。
    _clone: function (payload) {
      try {
        return JSON.parse(JSON.stringify(payload));
      } catch (error) {
        try {
          return String(payload);
        } catch (innerError) {
          return null;
        }
      }
    },

    // 记录一次云能力调用结果。
    _record: function (entryType, name, appId, data, result, status, error) {
      var entry = {
        type: entryType,
        name: name,
        appId: appId || "",
        data: data,
        timestamp: new Date().toLocaleTimeString(),
        ts: Date.now(),
        status: status || "pending"
      };
      if (result !== undefined) {
        entry.result = result;
      }
      if (error !== undefined) {
        entry.error = error;
      }
      this.hookedCalls.push(entry);
    },

    // 包装普通云方法，兼容 callback 与 Promise 两种返回形式。
    _wrapMethod: function (cloud, methodName, entryType, nameExtractor, originalStore, appId) {
      var original = cloud[methodName];
      if (!original || typeof original !== "function") {
        return false;
      }
      originalStore[methodName] = original.bind(cloud);
      var self = this;
      cloud[methodName] = function (options) {
        options = options || {};
        var callName = nameExtractor ? nameExtractor(options) : methodName;
        var callData = self._clone(options) || {};
        delete callData.success;
        delete callData.fail;
        delete callData.complete;
        delete callData.filePath;
        delete callData.tempFilePath;

        var recorded = false;
        var hadCallback = !!(options.success || options.fail);
        var originalSuccess = options.success;
        var originalFail = options.fail;

        options.success = function (response) {
          if (!recorded) {
            recorded = true;
            self._record(entryType, callName, appId, callData, self._clone(response), "success");
          }
          if (originalSuccess) {
            originalSuccess(response);
          }
        };
        options.fail = function (error) {
          if (!recorded) {
            recorded = true;
            self._record(
              entryType,
              callName,
              appId,
              callData,
              null,
              "fail",
              error ? (error.errMsg || JSON.stringify(error)) : "unknown"
            );
          }
          if (originalFail) {
            originalFail(error);
          }
        };

        var result = originalStore[methodName](options);
        if (!hadCallback && result && typeof result.then === "function") {
          result.then(function (response) {
            if (!recorded) {
              recorded = true;
              self._record(entryType, callName, appId, callData, self._clone(response), "success");
            }
          }).catch(function (error) {
            if (!recorded) {
              recorded = true;
              self._record(
                entryType,
                callName,
                appId,
                callData,
                null,
                "fail",
                error ? (error.errMsg || JSON.stringify(error)) : "unknown"
              );
            }
          });
        }
        return result;
      };
      return true;
    },

    // 包装数据库对象的终端调用。
    _wrapDbTerminal: function (target, methodName, entryType, name, appId, extraData) {
      var original = target[methodName];
      if (!original || typeof original !== "function") {
        return;
      }
      var bound = original.bind(target);
      var self = this;
      target[methodName] = function (options) {
        options = options || {};
        var callData = self._clone(extraData) || {};
        if (options && typeof options === "object" && options.data) {
          callData.data = self._clone(options.data);
        }
        var recorded = false;
        var hadCallback = !!(options.success || options.fail);
        var originalSuccess = options.success;
        var originalFail = options.fail;

        options.success = function (response) {
          if (!recorded) {
            recorded = true;
            self._record(entryType, name, appId, callData, self._clone(response), "success");
          }
          if (originalSuccess) {
            originalSuccess(response);
          }
        };
        options.fail = function (error) {
          if (!recorded) {
            recorded = true;
            self._record(
              entryType,
              name,
              appId,
              callData,
              null,
              "fail",
              error ? (error.errMsg || JSON.stringify(error)) : "unknown"
            );
          }
          if (originalFail) {
            originalFail(error);
          }
        };

        var result = bound(options);
        if (!hadCallback && result && typeof result.then === "function") {
          result.then(function (response) {
            if (!recorded) {
              recorded = true;
              self._record(entryType, name, appId, callData, self._clone(response), "success");
            }
          }).catch(function (error) {
            if (!recorded) {
              recorded = true;
              self._record(
                entryType,
                name,
                appId,
                callData,
                null,
                "fail",
                error ? (error.errMsg || JSON.stringify(error)) : "unknown"
              );
            }
          });
        }
        return result;
      };
    },

    // 对 `database().collection()` 相关对象继续追加 Hook。
    _hookDatabase: function (cloud, appId, originalStore) {
      var originalDatabase = cloud.database;
      if (!originalDatabase || typeof originalDatabase !== "function") {
        return;
      }
      originalStore.database = originalDatabase.bind(cloud);
      var self = this;

      cloud.database = function (options) {
        var db = originalStore.database(options);
        if (!db || !db.collection) {
          return db;
        }
        var originalCollection = db.collection.bind(db);
        db.collection = function (collectionName) {
          var collection = originalCollection(collectionName);
          if (!collection) {
            return collection;
          }
          ["add", "get", "update", "remove", "count"].forEach(function (methodName) {
            if (collection[methodName]) {
              self._wrapDbTerminal(collection, methodName, "db." + methodName, collectionName, appId, {});
            }
          });
          if (collection.doc) {
            var originalDoc = collection.doc.bind(collection);
            collection.doc = function (docId) {
              var docRef = originalDoc(docId);
              if (!docRef) {
                return docRef;
              }
              ["get", "update", "set", "remove"].forEach(function (methodName) {
                if (docRef[methodName]) {
                  self._wrapDbTerminal(docRef, methodName, "db.doc." + methodName, collectionName + "/" + docId, appId, {});
                }
              });
              return docRef;
            };
          }
          if (collection.where) {
            var originalWhere = collection.where.bind(collection);
            collection.where = function (condition) {
              var whereRef = originalWhere(condition);
              if (!whereRef) {
                return whereRef;
              }
              ["get", "update", "remove", "count"].forEach(function (methodName) {
                if (whereRef[methodName]) {
                  self._wrapDbTerminal(
                    whereRef,
                    methodName,
                    "db.where." + methodName,
                    collectionName,
                    appId,
                    { where: self._clone(condition) }
                  );
                }
              });
              return whereRef;
            };
          }
          if (collection.aggregate) {
            var originalAggregate = collection.aggregate.bind(collection);
            collection.aggregate = function () {
              var aggregate = originalAggregate();
              if (aggregate && aggregate.end) {
                self._wrapDbTerminal(aggregate, "end", "db.aggregate", collectionName, appId, {});
              }
              return aggregate;
            };
          }
          return collection;
        };
        return db;
      };
    },

    // 对单个 `wx.cloud` 实例安装 Hook。
    _hookCloudInstance: function (cloud, appId) {
      var originalStore = {};
      var knownMethods = {
        callFunction: { type: "function", getName: function (options) { return options.name || "unknown"; } },
        uploadFile: { type: "storage", getName: function (options) { return "uploadFile: " + (options.cloudPath || ""); } },
        downloadFile: { type: "storage", getName: function (options) { return "downloadFile: " + (options.fileID || ""); } },
        deleteFile: { type: "storage", getName: function (options) { return "deleteFile(" + ((options.fileList || []).length) + ")"; } },
        getTempFileURL: { type: "storage", getName: function (options) { return "getTempFileURL(" + ((options.fileList || []).length) + ")"; } },
        callContainer: { type: "container", getName: function (options) { return options.path || "callContainer"; } },
        connectContainer: { type: "container", getName: function (options) { return "connectContainer: " + (options.service || ""); } }
      };
      var methodNames = [];
      var index = 0;
      var key = "";

      try {
        methodNames = Object.keys(cloud);
      } catch (error) {}
      try {
        var proto = Object.getPrototypeOf(cloud);
        if (proto) {
          var protoKeys = Object.getOwnPropertyNames(proto);
          for (index = 0; index < protoKeys.length; index += 1) {
            if (methodNames.indexOf(protoKeys[index]) < 0) {
              methodNames.push(protoKeys[index]);
            }
          }
        }
      } catch (error) {}

      for (index = 0; index < methodNames.length; index += 1) {
        key = methodNames[index];
        if (!key || key.charAt(0) === "_" || key === "database" || key === "constructor") {
          continue;
        }
        try {
          if (typeof cloud[key] !== "function") {
            continue;
          }
        } catch (error) {
          continue;
        }
        var known = knownMethods[key];
        var entryType = known ? known.type : "cloud";
        var nameExtractor = known ? known.getName : (function (methodName) {
          return function () {
            return methodName;
          };
        })(key);
        this._wrapMethod(cloud, key, entryType, nameExtractor, originalStore, appId);
      }

      this._hookDatabase(cloud, appId, originalStore);
      this._hookedClouds.push({
        cloud: cloud,
        appId: appId,
        origMethods: originalStore
      });
    },

    // 自动扫描 frame，把新的 `wx.cloud` 实例全部接管。
    autoHookScan: function () {
      var frames = this._findFrames();
      var hookedApps = [];
      for (var frameIndex = 0; frameIndex < frames.length; frameIndex += 1) {
        var frame = frames[frameIndex];
        try {
          if (!frame.wx || !frame.wx.cloud) {
            continue;
          }
          var cloud = frame.wx.cloud;
          var alreadyHooked = false;
          for (var cloudIndex = 0; cloudIndex < this._hookedClouds.length; cloudIndex += 1) {
            if (this._hookedClouds[cloudIndex].cloud === cloud) {
              alreadyHooked = true;
              break;
            }
          }
          if (alreadyHooked) {
            continue;
          }
          var appId = this._appIdFromFrame(frame);
          this._hookCloudInstance(cloud, appId);
          hookedApps.push(appId);
        } catch (error) {}
      }
      return hookedApps;
    },

    // 对外提供环境探测结果，便于上层展示。
    detectEnv: function () {
      var frames = this._findFrames();
      var apps = [];
      for (var index = 0; index < frames.length; index += 1) {
        try {
          if (!frames[index].wx || !frames[index].wx.cloud) {
            continue;
          }
          apps.push({
            appId: this._appIdFromFrame(frames[index])
          });
        } catch (error) {}
      }
      return {
        ok: apps.length > 0,
        apps: apps,
        appId: apps.length > 0 ? apps[0].appId : ""
      };
    },

    // 安装动态 Hook 并启动自动补扫。
    installHook: function () {
      var hookedApps = this.autoHookScan();
      if (this._hookedClouds.length === 0) {
        this._hooked = false;
        return { ok: false, reason: "wx.cloud not available in any frame" };
      }
      this._hooked = true;
      this._startAutoScan();
      return {
        ok: true,
        totalHooked: this._hookedClouds.length,
        hookedApps: hookedApps
      };
    },

    // 定时扫描新 frame，避免页面切换后漏掉新的 `wx.cloud` 实例。
    _startAutoScan: function () {
      if (this._autoHookTimer) {
        return;
      }
      var self = this;
      this._autoHookTimer = setInterval(function () {
        self.autoHookScan();
      }, 3000);
    },

    // 停止自动补扫定时器。
    stopAutoHook: function () {
      if (!this._autoHookTimer) {
        return;
      }
      clearInterval(this._autoHookTimer);
      this._autoHookTimer = null;
    },

    // 卸载 Hook 并恢复原始方法。
    uninstallHook: function () {
      this.stopAutoHook();
      for (var index = 0; index < this._hookedClouds.length; index += 1) {
        var entry = this._hookedClouds[index];
        try {
          for (var methodName in entry.origMethods) {
            entry.cloud[methodName] = entry.origMethods[methodName];
          }
        } catch (error) {}
      }
      this._hookedClouds = [];
      this._hooked = false;
    },

    // 返回当前缓存的动态捕获记录。
    getHookedCalls: function () {
      return this.hookedCalls.slice();
    },

    // 清空当前缓存的动态捕获记录。
    clearHookedCalls: function () {
      this.hookedCalls = [];
    },

    // 手动调用目标小程序中的 `wx.cloud.callFunction`。
    callFunction: function (name, data, timeoutMs) {
      var self = this;
      var caller = null;
      for (var index = 0; index < this._hookedClouds.length; index += 1) {
        var entry = this._hookedClouds[index];
        if (entry.origMethods.callFunction) {
          caller = entry.origMethods.callFunction;
          break;
        }
      }
      if (!caller) {
        var frames = this._findFrames();
        for (var frameIndex = 0; frameIndex < frames.length; frameIndex += 1) {
          try {
            if (frames[frameIndex].wx && frames[frameIndex].wx.cloud && frames[frameIndex].wx.cloud.callFunction) {
              caller = frames[frameIndex].wx.cloud.callFunction.bind(frames[frameIndex].wx.cloud);
              break;
            }
          } catch (error) {}
        }
      }
      if (!caller) {
        return Promise.resolve({ ok: false, status: "fail", reason: "wx.cloud not available" });
      }
      return new Promise(function (resolve) {
        var settled = false;
        var callData = data || {};
        var timeoutDelay = typeof timeoutMs === "number" && timeoutMs > 0 ? timeoutMs : 10000;
        function finish(payload) {
          if (settled) {
            return;
          }
          settled = true;
          clearTimeout(timeout);
          resolve(payload);
        }
        function successPayload(response) {
          var result = null;
          try {
            result = self._clone(response && response.result ? response.result : response);
          } catch (error) {
            result = String(response);
          }
          return {
            ok: true,
            status: "success",
            name: name,
            data: callData,
            result: result
          };
        }
        function failPayload(error) {
          return {
            ok: false,
            status: "fail",
            name: name,
            data: callData,
            error: error ? (error.errMsg || error.message || JSON.stringify(error)) : "unknown"
          };
        }
        var timeout = setTimeout(function () {
          finish({ ok: false, status: "timeout", name: name, data: callData, reason: "调用超时(" + Math.round(timeoutDelay / 1000) + "s)" });
        }, timeoutDelay);
        try {
          var returned = caller({
            name: name,
            data: callData,
            success: function (response) {
              finish(successPayload(response));
            },
            fail: function (error) {
              finish(failPayload(error));
            }
          });
          if (returned && typeof returned.then === "function") {
            returned.then(function (response) {
              finish(successPayload(response));
            }).catch(function (error) {
              finish(failPayload(error));
            });
          }
        } catch (error) {
          finish(failPayload(error));
        }
      });
    }
  };

  window.cloudAudit = cloudAudit;
})();
