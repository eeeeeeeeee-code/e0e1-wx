"""
Port of RemoteDebugConstants.js - Protocol constants for WeChat Remote Debug.
"""


class ResponseType:
    Heartbeat = 2001
    Login = 2002
    EventNotifyBegin = 3001
    EventNotifyEnd = 3002
    EventNotifyBlock = 3003
    JoinRoom = 2003
    SendDebugMessage = 2000
    SendDebugMessageParallelly = 2006
    QuitRoom = 2004
    MessageNotify = 1000
    MessageNotifyParallelly = 1006
    SyncMessage = 2005
    Unknown = -1


class CompressAlgo:
    Non = 0
    Zlib = 1


class RequestType:
    Heartbeat = 2001
    Login = 2002
    EventNotifyBegin = 3001
    EventNotifyEnd = 3002
    EventNotifyBlock = 3003
    JoinRoom = 2003
    SendDebugMessage = 2000
    SendDebugMessageParallelly = 2006
    QuitRoom = 2004
    MessageNotify = 1000
    MessageNotifyParallelly = 1006
    SyncMessage = 2005
    Unknown = -1


class ClientRequestType:
    Heartbeat = 1001
    Login = 1002
    EventNotifyBegin = 3001
    EventNotifyEnd = 3002
    EventNotifyBlock = 3003
    JoinRoom = 1003
    SendDebugMessage = 1000
    SendDebugMessageParallelly = 1006
    QuitRoom = 1004
    MessageNotify = 2000
    MessageNotifyParallelly = 2006
    SyncMessage = 1005
    Unknown = -1


class ClientResponseType:
    Heartbeat = 1001
    Login = 1002
    EventNotifyBegin = 3001
    EventNotifyEnd = 3002
    EventNotifyBlock = 3003
    JoinRoom = 1003
    SendDebugMessage = 1000
    SendDebugMessageParallelly = 1006
    QuitRoom = 1004
    MessageNotify = 2000
    MessageNotifyParallelly = 2006
    SyncMessage = 1005
    Unknown = -1


class RequestCmd:
    Heartbeat = 2001
    Login = 2002
    EventNotifyBegin = 3001
    EventNotifyEnd = 3002
    EventNotifyBlock = 3003
    JoinRoom = 2003
    SendDebugMessage = 2000
    SendDebugMessageParallelly = 2006
    QuitRoom = 2004
    MessageNotify = 1000
    MessageNotifyParallelly = 1006
    SyncMessage = 2005
    Unknown = -1


class ClientRequestCmd:
    Heartbeat = 1001
    Login = 1002
    EventNotifyBegin = 3001
    EventNotifyEnd = 3002
    EventNotifyBlock = 3003
    JoinRoom = 1003
    SendDebugMessage = 1000
    SendDebugMessageParallelly = 1006
    QuitRoom = 1004
    MessageNotify = 2000
    MessageNotifyParallelly = 2006
    SyncMessage = 1005
    Unknown = -1


class DebugMessageCategory:
    SetupContext = "setupContext"
    CallInterface = "callInterface"
    EvaluateJavascript = "evaluateJavascript"
    CallInterfaceResult = "callInterfaceResult"
    EvaluateJavascriptResult = "evaluateJavascriptResult"
    Breakpoint = "breakpoint"
    Ping = "ping"
    Pong = "pong"
    DomOp = "domOp"
    DomEvent = "domEvent"
    NetworkDebugAPI = "networkDebugAPI"
    ChromeDevtools = "chromeDevtools"
    ChromeDevtoolsResult = "chromeDevtoolsResult"
    AddJsContext = "addJsContext"
    RemoveJsContext = "removeJsContext"
    ConnectJsContext = "connectJsContext"
    EngineEvent = "engineEvent"
    EngineOp = "engineOp"
    CustomMessage = "customMessage"


class KnownErrorCode:
    OK = 0
    ERR_SYS = -1
    NOT_EXIST = 1
    INVALID_ARGS = -2
    SYSTEM_BUSY = -3
    INVALID_LOGIN_TICKET = -50001
    HAS_NO_PERMISSION = -50002
    ROOM_IN_DEBUGGING = -50003
    NO_EXIST_ROOM = -50004
    MD5_NOT_MATCH = -50005
    USER_IN_DEBUGGING = -50006
    SEQ_ERROR = -50010
    SEND_MSG_BUSY = -50011
    SEND_MSG_SEQ_RANGE_ERROR = -50012
