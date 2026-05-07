"""调试开关运行时脚本封装。"""

from __future__ import annotations

import json


_FRAME_DETECT_JS = (
    "function detectFrame(){"
    " if(typeof wx!=='undefined'&&typeof getCurrentPages!=='undefined'){return window;}"
    " if(window.frames){"
    "  for(var i=0;i<window.frames.length;i+=1){"
    "   try{if(window.frames[i].wx&&window.frames[i].__wxConfig){return window.frames[i];}}catch(error){}"
    "  }"
    " }"
    " try{"
    "  if(window.parent&&window.parent.frames){"
    "   for(var j=0;j<window.parent.frames.length;j+=1){"
    "    try{if(window.parent.frames[j].wx&&window.parent.frames[j].__wxConfig){return window.parent.frames[j];}}catch(error){}"
    "   }"
    "  }"
    " }catch(error){}"
    " return null;"
    "}"
)


class DebugToggleRuntime:
    """封装调试开关相关的运行时检测与桥调用。"""

    def __init__(self, bridge, route_navigator) -> None:
        """保存桥对象与路由导航器，复用已有注入能力。"""
        self.bridge = bridge
        self.route_navigator = route_navigator

    async def detect(self) -> dict:
        """强制确保导航桥已注入后，基于真实小程序 frame 检测调试状态。"""
        await self.route_navigator.ensure_injected(force=True)
        payload = await self._evaluate_json(self._detect_expression(), action_name="detect")
        return {
            "debug_enabled": bool(payload.get("debug")),
            "vconsole_visible": bool(payload.get("vconsole")),
        }

    async def set_enabled(self, enabled: bool) -> dict:
        """强制确保导航桥已注入后，调用 wx.setEnableDebug 切换调试开关。"""
        await self.route_navigator.ensure_injected(force=True)
        return await self._call_bridge_json(self._set_enabled_expression(enabled), action_name="set_enabled")

    async def _evaluate_json(self, expression: str, *, action_name: str) -> dict:
        """执行表达式，并把桥返回的 JSON 字符串解析为字典。"""
        result = await self.bridge.evaluate_js(f"JSON.stringify({expression})", timeout=5.0)
        return self._load_json_response(result, action_name=action_name)

    async def _call_bridge_json(self, expression: str, *, action_name: str) -> dict:
        """通过 CDP 执行异步表达式，并把返回 JSON 字符串解析为字典。"""
        result = await self.bridge.send_cdp_command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
            timeout=5.0,
        )
        return self._load_json_response(result, action_name=action_name)

    @staticmethod
    def _detect_expression() -> str:
        """生成基于真实小程序 frame 的调试状态检测表达式。"""
        return (
            "(function(){"
            f"{_FRAME_DETECT_JS}"
            "var frame=detectFrame();"
            "if(!frame){return {err:'no wxFrame'};}"
            "return {"
            " debug:!!(frame.__wxConfig&&frame.__wxConfig.debug),"
            " vconsole:!!(frame.document&&frame.document.getElementById('__vconsole'))"
            "};"
            "})()"
        )

    @staticmethod
    def _set_enabled_expression(enabled: bool) -> str:
        """生成用于调用 wx.setEnableDebug 的运行时表达式。"""
        enable_flag = "true" if enabled else "false"
        return (
            "(async function(){"
            f"{_FRAME_DETECT_JS}"
            "var frame=detectFrame();"
            "if(!frame){return JSON.stringify({err:'no wxFrame'});}"
            "return await new Promise(function(resolve){"
            " frame.wx.setEnableDebug({"
            f"  enableDebug:{enable_flag},"
            "  success:function(result){"
            "   resolve(JSON.stringify(result&&typeof result==='object'?result:{ok:true}));"
            "  },"
            "  fail:function(error){"
            "   var message=(error&&error.errMsg)||String(error||'setEnableDebug failed');"
            "   resolve(JSON.stringify({err:message}));"
            "  }"
            " });"
            "});"
            "})()"
        )

    @staticmethod
    def _load_json_response(result: dict, *, action_name: str) -> dict:
        """从桥返回结构中提取 JSON 结果，并统一转换为运行时错误。"""
        error_message = DebugToggleRuntime._extract_error_message(result)
        if error_message:
            raise RuntimeError(str(error_message))
        value = DebugToggleRuntime._extract_value(result)
        if not value:
            raise RuntimeError(f"{action_name} bridge returned empty value")
        if isinstance(value, dict):
            payload = value
        else:
            try:
                payload = json.loads(value)
            except (TypeError, json.JSONDecodeError) as error:
                raise RuntimeError(f"{action_name} bridge returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise RuntimeError(f"{action_name} bridge returned invalid JSON")
        if payload.get("err"):
            raise RuntimeError(str(payload.get("err")))
        return payload

    @staticmethod
    def _extract_error_message(result: dict):
        """优先从 CDP 执行结果里提取更真实的异常原因。"""
        if not isinstance(result, dict):
            return None
        exception_details = result.get("exceptionDetails")
        if isinstance(exception_details, dict):
            exception = exception_details.get("exception")
            if isinstance(exception, dict):
                description = exception.get("description")
                if description:
                    return description
            text = exception_details.get("text")
            if text:
                return text
        remote_result = result.get("result", {}).get("result", {})
        if isinstance(remote_result, dict):
            description = remote_result.get("description")
            if description:
                return description
            value = remote_result.get("value")
            if isinstance(value, dict) and value.get("err"):
                return value.get("err")
        return None

    @staticmethod
    def _extract_value(result: dict):
        """从 CDP 或 evaluate_js 返回结构中提取 value 字段。"""
        if not isinstance(result, dict):
            return None
        return result.get("result", {}).get("result", {}).get("value")
