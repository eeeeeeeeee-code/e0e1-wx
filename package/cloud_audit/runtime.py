"""提供 DevTools worker 内部使用的动态云审计运行时封装。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from package.config.defaults import normalize_cloud_call_timeout
from package.cloud_audit.scanner import CloudSourceScanner


INJECT_SCRIPT_PATH = Path(__file__).with_name("inject.js")
_INJECT_SCRIPT_CACHE = ""


def cloud_call_transport_timeout(timeout_seconds: float) -> float:
    """在业务超时外增加 CDP 传输缓冲，避免临界返回被外层覆盖。"""
    base_timeout = float(timeout_seconds or 0.0)
    grace_seconds = max(0.4, min(base_timeout * 0.2, 3.0))
    return base_timeout + grace_seconds


class CloudAuditRuntime:
    """在当前小程序调试上下文中管理动态 Hook、轮询和手动调用。"""

    def __init__(self, bridge) -> None:
        """保存 bridge 引用，并初始化注入状态。"""
        self.bridge = bridge
        self._injected = False
        self._enabled = False
        self._seen_count = 0

    async def inject(self, force: bool = False) -> None:
        """按需把云审计注入脚本加载到当前小程序上下文。"""
        if force or not self._injected:
            await self.bridge.evaluate_js(await self.inject_script(), timeout=10.0)
            self._injected = True

    async def inject_script(self) -> str:
        """在线程中读取 UTF-8 注入脚本，避免导入时执行文件 IO。"""
        global _INJECT_SCRIPT_CACHE
        if not _INJECT_SCRIPT_CACHE:
            _INJECT_SCRIPT_CACHE = await asyncio.to_thread(INJECT_SCRIPT_PATH.read_text, encoding="utf-8")
        return _INJECT_SCRIPT_CACHE

    async def start(self) -> dict:
        """启动动态 Hook，并重置本地增量游标。"""
        self._enabled = False
        self._seen_count = 0
        await self.inject(force=True)
        result = await self.evaluate_json("window.cloudAudit.installHook()", timeout=8.0)
        if isinstance(result, dict) and bool(result.get("ok")):
            self._enabled = True
        return result if isinstance(result, dict) else {"ok": False, "reason": "hook start failed"}

    async def stop(self) -> None:
        """停止动态 Hook，并恢复原始云方法。"""
        if not self._enabled and not self._injected:
            return
        try:
            await self.inject(force=True)
            await self.bridge.evaluate_js("window.cloudAudit.uninstallHook()", timeout=5.0)
        finally:
            self._enabled = False
            self._seen_count = 0

    async def clear(self) -> None:
        """清空当前上下文中的已捕获记录。"""
        self._seen_count = 0
        await self.inject(force=True)
        await self.bridge.evaluate_js("window.cloudAudit.clearHookedCalls()", timeout=3.0)

    async def poll(self) -> list[dict]:
        """拉取新的动态 Hook 记录，并在上下文切换后自动重装 Hook。"""
        if not self._enabled:
            return []
        await self.inject(force=True)
        alive = await self.evaluate_value(
            "(function(){return String(!!(window.cloudAudit && window.cloudAudit._hooked));})()",
            timeout=3.0,
        )
        if str(alive or "") != "true":
            start_result = await self.evaluate_json("window.cloudAudit.installHook()", timeout=8.0)
            if not isinstance(start_result, dict) or not bool(start_result.get("ok")):
                self._enabled = False
                return []
            self._enabled = True
            self._seen_count = 0
        calls = await self.evaluate_json("window.cloudAudit.getHookedCalls()", timeout=5.0)
        if not isinstance(calls, list) or len(calls) <= self._seen_count:
            return []
        new_calls = calls[self._seen_count :]
        self._seen_count = len(calls)
        return [dict(item) for item in new_calls if isinstance(item, dict)]

    async def static_scan(self, on_progress=None) -> list[dict]:
        """从运行时源码和调试脚本中补齐静态扫描结果。"""
        await self.inject()
        sources = await self.collect_static_sources()
        if on_progress is not None:
            on_progress(f"已收集 {len(sources)} 个运行时源码片段，开始静态扫描")

        def report(summary: dict) -> None:
            if on_progress is None:
                return
            try:
                scanned_files = int(summary.get("scanned_files") or 0)
                total_files = int(summary.get("total_files") or 0)
                match_count = int(summary.get("match_count") or 0)
            except Exception:
                on_progress("静态扫描中...")
                return
            on_progress(f"静态扫描中... {scanned_files}/{total_files}，发现 {match_count} 项")

        scanner = CloudSourceScanner(progress_callback=report if on_progress is not None else None)
        results = scanner.scan_sources(sources)
        if on_progress is not None:
            on_progress(f"静态扫描完成，发现 {len(results)} 个结果")
        return results

    async def collect_static_sources(self) -> list[dict]:
        """收集可用于静态扫描的运行时源码片段。"""
        sources: list[dict] = []
        try:
            runtime_sources = await self.evaluate_json(self.runtime_sources_expression(), timeout=8.0)
        except Exception:
            runtime_sources = None
        if isinstance(runtime_sources, list):
            for index, item in enumerate(runtime_sources):
                if not isinstance(item, dict):
                    continue
                source_text = str(item.get("source") or "")
                if not source_text:
                    continue
                source_name = str(item.get("name") or item.get("path") or f"runtime:{index}")
                sources.append({"name": source_name, "source": source_text})
        sources.extend(await self.collect_debugger_sources())
        deduped: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for item in sources:
            source_name = str(item.get("name") or "")
            source_text = str(item.get("source") or "")
            if not source_text:
                continue
            key = (source_name, source_text)
            if key in seen:
                continue
            seen.add(key)
            deduped.append({"name": source_name, "source": source_text})
        return deduped

    async def collect_debugger_sources(self) -> list[dict]:
        """通过 CDP Debugger 再抓一轮已加载脚本源码。"""
        if not hasattr(self.bridge, "on_cdp_event") or not hasattr(self.bridge, "off_cdp_event"):
            return []

        script_ids: list[tuple[str, str]] = []

        def on_script_parsed(event: dict) -> None:
            params = event.get("params", {}) if isinstance(event, dict) else {}
            script_id = params.get("scriptId")
            if script_id is None:
                return
            script_ids.append((str(script_id), str(params.get("url") or "")))

        self.bridge.on_cdp_event("Debugger.scriptParsed", on_script_parsed)
        try:
            try:
                await self.bridge.send_cdp_command("Debugger.disable", timeout=3.0)
            except Exception:
                pass
            try:
                await self.bridge.send_cdp_command("Debugger.enable", timeout=5.0)
            except Exception:
                return []

            previous_count = -1
            for _ in range(5):
                await asyncio.sleep(0.3)
                if len(script_ids) == previous_count and previous_count > 0:
                    break
                previous_count = len(script_ids)

            sources: list[dict] = []
            seen_ids: set[str] = set()
            for script_id, url in script_ids:
                if script_id in seen_ids:
                    continue
                seen_ids.add(script_id)
                try:
                    response = await self.bridge.send_cdp_command(
                        "Debugger.getScriptSource",
                        {"scriptId": script_id},
                        timeout=8.0,
                    )
                except Exception:
                    continue
                source_text = str(response.get("result", {}).get("scriptSource") or "")
                if not source_text:
                    continue
                sources.append({"name": f"cdp:{url or script_id}", "source": source_text})
            return sources
        finally:
            try:
                await self.bridge.send_cdp_command("Debugger.disable", timeout=3.0)
            except Exception:
                pass
            self.bridge.off_cdp_event("Debugger.scriptParsed", on_script_parsed)

    @staticmethod
    def runtime_sources_expression() -> str:
        """生成从 __wxAppCode__ 中提取源码的运行时表达式。"""
        return r"""
(function() {
  function findAllFrames() {
    var frames = [];
    var seen = [];
    function tryAdd(w) {
      try {
        if (!w) return;
        for (var i = 0; i < seen.length; i++) {
          if (seen[i] === w) return;
        }
        seen.push(w);
        frames.push(w);
      } catch (e) {}
    }
    tryAdd(window);
    var sources = [window];
    try {
      if (window.parent && window.parent !== window) sources.push(window.parent);
    } catch (e) {}
    for (var s = 0; s < sources.length; s++) {
      try {
        var src = sources[s];
        if (src && src.frames) {
          for (var i = 0; i < src.frames.length; i++) {
            tryAdd(src.frames[i]);
          }
        }
      } catch (e) {}
    }
    return frames;
  }

  function toSource(value) {
    try {
      if (typeof value === 'string') return value;
      if (typeof value === 'function') return value.toString();
    } catch (e) {}
    return '';
  }

  var result = [];
  var frames = findAllFrames();
  for (var i = 0; i < frames.length; i++) {
    try {
      var code = frames[i].__wxAppCode__;
      if (!code) continue;
      for (var key in code) {
        if (!Object.prototype.hasOwnProperty.call(code, key)) continue;
        try {
          var src = toSource(code[key]);
          if (src) {
            result.push({ name: 'runtime:__wxAppCode__/' + String(key), source: src });
          }
        } catch (e) {}
      }
    } catch (e) {}
  }
  return result;
})()
"""

    async def call_function(self, name: str, data: dict | None = None, timeout_seconds: float = 5.0) -> dict:
        """通过注入脚本提供的 `window.cloudAudit.callFunction` 手动调用云函数。"""
        timeout_seconds = normalize_cloud_call_timeout(timeout_seconds, minimum=0.05, maximum=120)
        await self.inject(force=True)
        expression = (
            "(async function(){"
            f"return JSON.stringify(await window.cloudAudit.callFunction({json.dumps(str(name or ''))},"
            f" {json.dumps(data or {}, ensure_ascii=False)}, {json.dumps(timeout_seconds * 1000)}));"
            "})()"
        )
        try:
            result = await self.evaluate_value(
                expression,
                timeout=cloud_call_transport_timeout(float(timeout_seconds)),
                await_promise=True,
            )
        except asyncio.TimeoutError:
            return {
                "ok": False,
                "status": "timeout",
                "name": str(name or ""),
                "data": data or {},
                "timeout_seconds": timeout_seconds,
                "reason": f"调用超时({timeout_seconds}s)，请确认目标云函数是否返回或 DevTools 是否保持连接",
            }
        if not result:
            return {"ok": False, "status": "fail", "name": str(name or ""), "data": data or {}, "timeout_seconds": timeout_seconds, "reason": "调用无返回结果"}
        try:
            payload = json.loads(result)
        except json.JSONDecodeError:
            return {"ok": False, "status": "fail", "name": str(name or ""), "data": data or {}, "timeout_seconds": timeout_seconds, "reason": "返回结果解析失败"}
        if isinstance(payload, dict):
            payload.setdefault("name", str(name or ""))
            payload.setdefault("data", data or {})
            payload.setdefault("timeout_seconds", timeout_seconds)
        return payload

    async def evaluate_json(self, expression: str, timeout: float = 5.0) -> dict | list | None:
        """执行表达式并把 JSON 字符串结果反序列化为 Python 对象。"""
        value = await self.evaluate_value(f"JSON.stringify({expression})", timeout=timeout)
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    async def evaluate_value(self, expression: str, timeout: float = 5.0, await_promise: bool = False):
        """执行表达式并提取 CDP 返回值。"""
        if await_promise:
            result = await self.bridge.send_cdp_command(
                "Runtime.evaluate",
                {
                    "expression": expression,
                    "returnByValue": True,
                    "awaitPromise": True,
                },
                timeout=timeout,
            )
            return self.extract_value(result)
        result = await self.bridge.evaluate_js(expression, timeout=timeout)
        return self.extract_value(result)

    @staticmethod
    def extract_value(result: dict):
        """从 CDP Runtime.evaluate 返回结构中提取 `value` 字段。"""
        if not isinstance(result, dict):
            return None
        return result.get("result", {}).get("result", {}).get("value")
