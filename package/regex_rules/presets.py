"""定义面向小程序反编译结果的常用正则扫描预设。"""

from __future__ import annotations

import copy


_TLD = (
    r"xin|com|cn|net|com\.cn|vip|top|cc|shop|club|wang|xyz|site|online|"
    r"org|link|biz|tech|mobi|me|tv|co|info|work|group|software|cloud|"
    r"中国|公司|网络|在线|网址|网店|集团|中文网"
)

_DANGEROUS_EXT = (
    r"php|asp|aspx|jsp|do|action|cgi|ashx|asmx|py|pl|go|rb|jar|war|"
    r"html|htm|exe|msi|bat|cmd|sh|bash|vbs|ps1|dll|so|dylib|wasm"
)

_STATIC_EXT = (
    r"css|js|ts|json|config|xml|vue|jsx|tsx|txt|csv|png|jpg|jpeg|gif|"
    r"webp|svg|ico|bmp|mp3|wav|ogg|mp4|webm|mov|avi|pdf|doc|docx|xls|"
    r"xlsx|ppt|pptx|woff|woff2|ttf|eot|zip|rar|7z|tar|gz|tgz"
)

_SECRET_KEYS = (
    r"password|passwd|pwd|username|user|admin_?pass|admin_?pwd|secret|"
    r"secret_?key|client_?secret|app_?secret|api_?secret|api_?key|apikey|"
    r"appkey|app_?key|access_?token|auth_?token|oauth_?token|refresh_?token|"
    r"bearer|authorization|access_?key|accesskeyid|accesskeysecret|"
    r"secretaccesskey|secretid|secretkey|ak|sk|bucket|private_?key|"
    r"github_?token|gitlab_?token|npm_?token|snyk_?token|sonar_?token|"
    r"sendgrid_?api_?key|mailgun_?api_?key|stripe_?secret_?key|"
    r"twilio_?token|firebase_?key|google_?api_?key"
)


DEFAULT_REGEX_RULES = [
    {
        "name": "身份证号",
        "pattern": r"\b[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b",
        "enabled": True,
        "note": "匹配中国大陆 18 位身份证号。",
    },
    {
        "name": "手机号",
        "pattern": r"\b1[3-9]\d{9}\b",
        "enabled": True,
        "note": "匹配中国大陆手机号。",
    },
    {
        "name": "邮箱",
        "pattern": r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,61}\b",
        "enabled": True,
        "note": "匹配常见邮箱地址。",
    },
    {
        "name": "IPv4",
        "pattern": r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?::\d{1,5})?\b",
        "enabled": True,
        "note": "匹配 IPv4 和可选端口。",
    },
    {
        "name": "域名",
        "pattern": r"\b(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+(?:" + _TLD + r")(?::\d{1,5})?\b",
        "enabled": True,
        "note": "匹配常见域名，包含部分中文 TLD。",
    },
    {
        "name": "URL 接口",
        "pattern": r"https?://[^\s'\"<>]+(?:\.(?:" + _DANGEROUS_EXT + r"))?(?:\?[^\s'\"<>]*)?",
        "enabled": True,
        "note": "匹配 HTTP/HTTPS 接口、页面和高风险扩展路径。",
    },
    {
        "name": "路径接口",
        "pattern": r"(?<![A-Za-z0-9_])(?:/|\./|\.\./)[A-Za-z0-9_\-./{}:]+(?:\?[A-Za-z0-9_\-./%=&{}:]+)?",
        "enabled": True,
        "note": "匹配本地相对路径、绝对路径和接口路径。",
    },
    {
        "name": "静态资源",
        "pattern": r"(?:https?://[^\s'\"<>]+|(?:/|\./|\.\./)[^\s'\"<>]+)\.(?:" + _STATIC_EXT + r")(?:\?[^\s'\"<>]*)?",
        "enabled": True,
        "note": "匹配 JS、CSS、图片、文档和压缩包等静态资源。",
    },
    {
        "name": "JWT Token",
        "pattern": r"\beyJ[A-Za-z0-9_/+\-]{10,}={0,2}\.[A-Za-z0-9_/+\-]{10,}={0,2}\.[A-Za-z0-9_/+\-]{10,}={0,2}\b",
        "enabled": True,
        "note": "匹配标准三段式 JWT。",
    },
    {
        "name": "Bearer Token",
        "pattern": r"\b[Bb]earer\s+[A-Za-z0-9\-_=._+/\\]{20,500}\b",
        "enabled": True,
        "note": "匹配 Authorization Bearer Token。",
    },
    {
        "name": "Basic Token",
        "pattern": r"\b[Bb]asic\s+[A-Za-z0-9+/]{18,}={0,2}\b",
        "enabled": True,
        "note": "匹配 Basic Authorization Token。",
    },
    {
        "name": "敏感字段赋值",
        "pattern": r"(?i)\b(?:" + _SECRET_KEYS + r")\b[\"'\]]*\s*[:=]\s*[\"']?[^\"'\s,;]{5,500}[\"']?",
        "enabled": True,
        "note": "合并 Nuclei/常见 key 名，匹配密码、Token、Key、Secret 等字段赋值。",
    },
    {
        "name": "硬编码账号密码",
        "pattern": r"(?i)\b(?:admin_?pass|password|passwd|pwd|user_?pass|user_?pwd|admin_?pwd|username|user)\b\s*[:=]\s*[\"']?[^\"'\s,;]{3,100}[\"']?",
        "enabled": True,
        "note": "匹配常见硬编码账号密码字段。",
    },
    {
        "name": "私钥块",
        "pattern": r"-----\s*BEGIN[ A-Z0-9_-]*PRIVATE KEY\s*-----[\s\S]{20,}?-----\s*END[ A-Z0-9_-]*PRIVATE KEY\s*-----",
        "enabled": True,
        "note": "匹配 PEM 私钥块。",
    },
    {
        "name": "云厂商 AK",
        "pattern": r"\b(?:LTAI[A-Za-z\d]{12,30}|AKID[A-Za-z\d]{13,40}|JDC_[0-9A-Z]{25,40}|(?:AKLT|AKTP)[A-Za-z0-9]{35,50}|AKLT[A-Za-z0-9\-_]{16,28}|(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16})\b",
        "enabled": True,
        "note": "匹配阿里云、腾讯云、京东云、火山、金山云和 AWS AccessKey。",
    },
    {
        "name": "Google API Key",
        "pattern": r"\bAIza[0-9A-Za-z_\-]{35}\b",
        "enabled": True,
        "note": "匹配 Google API Key。",
    },
    {
        "name": "Google OAuth",
        "pattern": r"\b(?:ya29\.[0-9A-Za-z\-_]+|[0-9]+-[0-9A-Za-z_]{32}\.apps\.googleusercontent\.com)\b",
        "enabled": True,
        "note": "匹配 Google OAuth Token 和 Client ID。",
    },
    {
        "name": "GitHub Token",
        "pattern": r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{36,255}\b",
        "enabled": True,
        "note": "匹配 GitHub Personal Access Token。",
    },
    {
        "name": "GitLab Token",
        "pattern": r"\bglpat-[A-Za-z0-9\-=_]{20,22}\b",
        "enabled": True,
        "note": "匹配 GitLab Personal Access Token。",
    },
    {
        "name": "Stripe Key",
        "pattern": r"\b[rs]k_live_[0-9A-Za-z]{24}\b",
        "enabled": True,
        "note": "匹配 Stripe Live Secret/Restricted Key。",
    },
    {
        "name": "Twilio Key",
        "pattern": r"\bSK[0-9a-fA-F]{32}\b",
        "enabled": True,
        "note": "匹配 Twilio API Key。",
    },
    {
        "name": "Mailgun Key",
        "pattern": r"\bkey-[0-9A-Za-z]{32}\b",
        "enabled": True,
        "note": "匹配 Mailgun API Key。",
    },
    {
        "name": "微信标识",
        "pattern": r"[\"'](?:wx[a-z0-9]{15,18}|ww[a-z0-9]{15,18}|gh_[a-z0-9]{11,13})[\"']",
        "enabled": True,
        "note": "匹配微信 AppID、企业微信 CorpID 和公众号 GH ID。",
    },
    {
        "name": "Webhook URL",
        "pattern": r"\b(?:https://qyapi\.weixin\.qq\.com/cgi-bin/webhook/send\?key=[A-Za-z0-9\-]{25,50}|https://oapi\.dingtalk\.com/robot/send\?access_token=[a-z0-9]{50,80}|https://open\.feishu\.cn/open-apis/bot/v2/hook/[a-z0-9\-]{25,50}|https://hooks\.slack\.com/services/[A-Za-z0-9\-_]{6,12}/[A-Za-z0-9\-_]{6,12}/[A-Za-z0-9\-_]{15,24})\b",
        "enabled": True,
        "note": "匹配企微、钉钉、飞书和 Slack Webhook。",
    },
    {
        "name": "OSS 云存储",
        "pattern": r"(?i)\b(?:[\w.-]+\.oss[\w-]*\.aliyuncs\.com|[\w.-]+\.cos\.[\w-]+\.myqcloud\.com|[\w.-]+\.file\.myqcloud\.com|(?:[\w.-]+\.)?s3[\w.-]*\.amazonaws\.com|[\w.-]+\.obs\.[\w-]+\.myhuaweicloud\.com|[\w.-]+\.(?:qiniucdn|qnssl)\.com|[\w.-]+\.bkt\.clouddn\.com|[\w.-]+\.blob\.core\.windows\.net|storage\.googleapis\.com(?:/[\w.-]+)?|[\w.-]+\.storage\.googleapis\.com|[\w.-]+\.cdn\.bcebos\.com|[\w.-]+\.vod[\w-]*\.aliyuncs\.com|[\w.-]+\.cdn\.aliyuncs\.com|[\w.-]+\.ucloud\.cn|[\w.-]+\.ks3[\w-]*\.ksyun\.com)\b",
        "enabled": True,
        "note": "匹配主流云存储和 CDN 域名。",
    },
    {
        "name": "地图服务 Key",
        "pattern": r"\b(?:webapi\.amap\.com|api\.map\.baidu\.com|apis\.map\.qq\.com|map\.qq\.com/api/|maps\.googleapis\.com)\b",
        "enabled": True,
        "note": "匹配高德、百度、腾讯、Google 地图服务入口。",
    },
    {
        "name": "加密算法调用",
        "pattern": r"(?i)\b(?:Base64\.encode|Base64\.decode|btoa|atob|CryptoJS\.AES|CryptoJS\.DES|JSEncrypt|rsa|KJUR|\$\.md5|md5|sha1|sha256|sha512)\s*[\(.]",
        "enabled": True,
        "note": "匹配前端常见编码、摘要和加密算法调用。",
    },
]


def normalized_rule_name(rule: dict) -> str:
    """获取规则名称，用于去重。"""
    return str(rule.get("name", "")).strip()


def copy_default_regex_rules() -> list[dict]:
    """返回默认正则规则的深拷贝，避免调用方修改全局预设。"""
    return copy.deepcopy(DEFAULT_REGEX_RULES)


def is_legacy_default_regex_rules(rules: list[dict]) -> bool:
    """判断当前规则是否为旧版本内置的默认正则规则。"""
    legacy_names = {"请求域名", "云函数入口"}
    names = {normalized_rule_name(rule) for rule in rules if normalized_rule_name(rule)}
    return bool(names) and names.issubset(legacy_names)
