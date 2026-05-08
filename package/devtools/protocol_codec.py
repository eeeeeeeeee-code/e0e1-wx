"""
Port of RemoteDebugCodex.js - Protocol encode/decode for WeChat Remote Debug.
Handles protobuf wrapping/unwrapping of debug messages.
"""
import zlib

from package.devtools.protocol_constants import CompressAlgo, DebugMessageCategory
from package.devtools.third_party import wmpf_debug_pb2 as proto


def wrap_debug_message_data(data: dict, category: str, compress_algo: int = 0):
    """
    Encode data into a protobuf debug message payload based on category.
    Returns dict with 'buffer' (bytes) and 'originalSize' (int).
    """
    buf = None

    if category == DebugMessageCategory.CallInterface:
        msg = proto.WARemoteDebug_CallInterface()
        msg.objName = data.get("name", "")
        msg.methodName = data.get("method", "")
        for arg in data.get("args", []):
            msg.methodArgList.append(str(arg))
        if "call_id" in data and data["call_id"] is not None:
            msg.callId = data["call_id"]
        buf = msg.SerializeToString()

    elif category == DebugMessageCategory.EvaluateJavascriptResult:
        msg = proto.WARemoteDebug_EvaluateJavascriptResult()
        if data.get("ret") is not None:
            msg.ret = data["ret"]
        if data.get("evaluate_id") is not None:
            msg.evaluateId = data["evaluate_id"]
        buf = msg.SerializeToString()

    elif category == DebugMessageCategory.Ping:
        msg = proto.WARemoteDebug_Ping()
        if data.get("ping_id") is not None:
            msg.pingId = data["ping_id"]
        if data.get("payload") is not None:
            msg.payload = data["payload"]
        buf = msg.SerializeToString()

    elif category == DebugMessageCategory.Breakpoint:
        msg = proto.WARemoteDebug_Breakpoint()
        msg.isHit = bool(data.get("is_hit", False))
        buf = msg.SerializeToString()

    elif category == DebugMessageCategory.DomOp:
        msg = proto.WARemoteDebug_DomOp()
        if data.get("params") is not None:
            msg.params = data["params"]
        if data.get("webview_id") is not None:
            msg.webviewId = data["webview_id"]
        buf = msg.SerializeToString()

    elif category == DebugMessageCategory.DomEvent:
        msg = proto.WARemoteDebug_DomEvent()
        if data.get("params") is not None:
            msg.params = data["params"]
        if data.get("webview_id") is not None:
            msg.webviewId = data["webview_id"]
        buf = msg.SerializeToString()

    elif category == DebugMessageCategory.ChromeDevtools:
        msg = proto.WARemoteDebug_ChromeDevtools()
        if data.get("op_id") is not None:
            msg.opId = data["op_id"]
        if data.get("payload") is not None:
            msg.payload = data["payload"]
        if data.get("jscontext_id") is not None:
            msg.jscontextId = data["jscontext_id"]
        buf = msg.SerializeToString()

    elif category == DebugMessageCategory.ConnectJsContext:
        msg = proto.WARemoteDebug_ConnectJsContext()
        if data.get("jscontext_id") is not None:
            msg.jscontextId = data["jscontext_id"]
        buf = msg.SerializeToString()

    elif category == DebugMessageCategory.CustomMessage:
        msg = proto.WARemoteDebug_CustomMessage()
        if data.get("method") is not None:
            msg.method = data["method"]
        if data.get("payload") is not None:
            msg.payload = data["payload"]
        if data.get("raw") is not None:
            msg.raw = data["raw"]
        buf = msg.SerializeToString()

    else:
        raise ValueError(f"invalid debug message category: {category}")

    original_size = 0
    if buf is not None and compress_algo and (compress_algo & CompressAlgo.Zlib) != 0:
        original_size = len(buf)
        buf = zlib.compress(buf)

    return {
        "buffer": buf,
        "originalSize": original_size,
    }


def unwrap_debug_message_data(msg) -> dict:
    """
    Decode a WARemoteDebug_DebugMessage protobuf object into a plain dict.
    msg can be a protobuf message object or a dict-like with fields:
      seq, after, category, data, compressAlgo, originalSize
    """
    raw_data = msg.data if hasattr(msg, "data") else msg.get("data", b"")
    category = msg.category if hasattr(msg, "category") else msg.get("category", "")
    compress_algo = msg.compressAlgo if hasattr(msg, "compressAlgo") else msg.get("compressAlgo", 0)
    seq = msg.seq if hasattr(msg, "seq") else msg.get("seq", 0)
    after = msg.after if hasattr(msg, "after") else msg.get("after", 0)
    original_size_field = msg.originalSize if hasattr(msg, "originalSize") else msg.get("originalSize", 0)

    if isinstance(raw_data, str):
        raw_data = raw_data.encode("latin-1")

    buf = raw_data
    compressed_size = 0
    if buf and compress_algo and (compress_algo & CompressAlgo.Zlib) != 0:
        compressed_size = len(buf)
        buf = zlib.decompress(buf)

    decoded = None

    if buf:
        if category == DebugMessageCategory.Breakpoint:
            m = proto.WARemoteDebug_Breakpoint()
            m.ParseFromString(buf)
            decoded = {"is_hit": 1 if m.isHit else 0}

        elif category == DebugMessageCategory.CallInterface:
            m = proto.WARemoteDebug_CallInterface()
            m.ParseFromString(buf)
            decoded = {
                "name": m.objName,
                "method": m.methodName,
                "args": list(m.methodArgList),
                "call_id": m.callId,
            }

        elif category == DebugMessageCategory.CallInterfaceResult:
            m = proto.WARemoteDebug_CallInterfaceResult()
            m.ParseFromString(buf)
            decoded = {
                "ret": m.ret,
                "call_id": m.callId,
                "debug_info": m.debugInfo,
            }

        elif category == DebugMessageCategory.EvaluateJavascript:
            m = proto.WARemoteDebug_EvaluateJavascript()
            m.ParseFromString(buf)
            decoded = {
                "script": m.script,
                "evaluate_id": m.evaluateId,
                "debug_info": m.debugInfo,
            }

        elif category == DebugMessageCategory.EvaluateJavascriptResult:
            m = proto.WARemoteDebug_EvaluateJavascriptResult()
            m.ParseFromString(buf)
            decoded = {
                "ret": m.ret,
                "evaluate_id": m.evaluateId,
            }

        elif category == DebugMessageCategory.Ping:
            m = proto.WARemoteDebug_Ping()
            m.ParseFromString(buf)
            decoded = {
                "ping_id": m.pingId,
                "payload": m.payload,
            }

        elif category == DebugMessageCategory.Pong:
            m = proto.WARemoteDebug_Pong()
            m.ParseFromString(buf)
            decoded = {
                "ping_id": m.pingId,
                "network_type": m.networkType,
                "payload": m.payload,
            }

        elif category == DebugMessageCategory.SetupContext:
            m = proto.WARemoteDebug_SetupContext()
            m.ParseFromString(buf)
            ri = m.registerInterface if m.HasField("registerInterface") else None
            di = m.deviceInfo if m.HasField("deviceInfo") else None
            decoded = {
                "register_interface": {
                    "obj_name": ri.objName if ri else "",
                    "obj_methods": [
                        {
                            "method_name": meth.methodName,
                            "method_args": list(meth.methodArgList),
                        }
                        for meth in (ri.objMethodList if ri else [])
                    ],
                } if ri else {},
                "configure_js": m.configureJs,
                "public_js_md5": m.publicJsMd5,
                "three_js_md5": m.threeJsMd5,
                "device_info": {
                    "device_name": di.deviceName if di else "",
                    "device_model": di.deviceModel if di else "",
                    "os": di.systemVersion if di else "",
                    "wechat_version": di.wechatVersion if di else "",
                    "pixel_ratio": di.pixelRatio if di else 0,
                    "screen_width": di.screenWidth if di else 0,
                    "publib": di.publibVersion if di else 0,
                    "user_agent": di.userAgent if di else "",
                } if di else {},
                "support_compress_algo": m.supportCompressAlgo,
            }

        elif category == DebugMessageCategory.DomOp:
            m = proto.WARemoteDebug_DomOp()
            m.ParseFromString(buf)
            decoded = {
                "params": m.params,
                "webview_id": m.webviewId,
            }

        elif category == DebugMessageCategory.DomEvent:
            m = proto.WARemoteDebug_DomEvent()
            m.ParseFromString(buf)
            decoded = {
                "params": m.params,
                "webview_id": m.webviewId,
            }

        elif category == DebugMessageCategory.NetworkDebugAPI:
            m = proto.WARemoteDebug_NetworkDebugAPI()
            m.ParseFromString(buf)
            decoded = {
                "api_name": m.apiName,
                "task_id": m.taskId,
                "request_headers": m.requestHeaders,
                "timestamp": m.timestamp,
            }

        elif category == DebugMessageCategory.ChromeDevtools:
            m = proto.WARemoteDebug_ChromeDevtools()
            m.ParseFromString(buf)
            decoded = {
                "op_id": m.opId,
                "payload": m.payload,
                "jscontext_id": m.jscontextId,
            }

        elif category == DebugMessageCategory.ChromeDevtoolsResult:
            m = proto.WARemoteDebug_ChromeDevtoolsResult()
            m.ParseFromString(buf)
            decoded = {
                "op_id": m.opId,
                "payload": m.payload,
                "jscontext_id": m.jscontextId,
            }

        elif category == DebugMessageCategory.AddJsContext:
            m = proto.WARemoteDebug_AddJsContext()
            m.ParseFromString(buf)
            decoded = {
                "jscontext_id": m.jscontextId,
                "jscontext_name": m.jscontextName,
            }

        elif category == DebugMessageCategory.RemoveJsContext:
            m = proto.WARemoteDebug_RemoveJsContext()
            m.ParseFromString(buf)
            decoded = {
                "jscontext_id": m.jscontextId,
            }

        elif category == DebugMessageCategory.ConnectJsContext:
            m = proto.WARemoteDebug_ConnectJsContext()
            m.ParseFromString(buf)
            decoded = {
                "jscontext_id": m.jscontextId,
            }

        elif category == DebugMessageCategory.CustomMessage:
            m = proto.WARemoteDebug_CustomMessage()
            m.ParseFromString(buf)
            decoded = {
                "method": m.method,
                "payload": m.payload,
                "raw": m.raw,
            }

        else:
            decoded = None

    return {
        "seq": seq or 0,
        "delay": after or 0,
        "category": category or DebugMessageCategory.Ping,
        "data": decoded or {},
        "compress_algo": compress_algo or 0,
        "original_size": original_size_field or compressed_size,
    }
