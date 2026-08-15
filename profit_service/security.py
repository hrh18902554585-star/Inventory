# -*- coding: utf-8 -*-
"""
token 鉴权 + 日志脱敏
- get_token: 读 data/token.txt，首次启动自动生成（secrets.token_urlsafe(24)）并打印
- check_request: 校验请求头 X-Api-Token
- sanitize/sanitize_dict: 正则脱敏（Cookie 值 / XSRF token / 15-22位订单号 / 敏感关键字）
"""
import os
import re
import secrets
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "data", "token.txt")

# 脱敏正则按序执行：Cookie → XSRF → 订单号 → 兜底
_RE_COOKIE = re.compile(r'(cookie\s*[=:]\s*["\']?)[^"\'\s,;]{8,}', re.IGNORECASE)
_RE_XSRF = re.compile(r'(xsrf[-_]?token|x-csrf[-_]?token)\s*[=:]\s*["\']?[^"\'\s;]+', re.IGNORECASE)
_RE_ORDER = re.compile(r'(?<!\d)\d{15,22}(?!\d)')
_RE_FALLBACK = re.compile(r'(?i)\b(secret|token|password|session)\b\s*[=:]\s*["\']?[^"\'\s,;]+')

_token_lock = threading.Lock()


def get_token() -> str:
    """读 data/token.txt；不存在则生成 secrets.token_urlsafe(24) 并写入"""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, encoding="utf-8") as f:
            tok = f.read().strip()
        if tok:
            return tok
    with _token_lock:
        # 双检：等锁期间可能已被其他线程生成
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, encoding="utf-8") as f:
                tok = f.read().strip()
            if tok:
                return tok
        tok = secrets.token_urlsafe(24)
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(tok)
        print(f"首次启动已生成访问令牌: {tok}（已写入 {TOKEN_FILE}）")
        return tok


def check_request(request) -> bool:
    """请求头 X-Api-Token 与 token.txt 一致即通过"""
    return request.headers.get("X-Api-Token") == get_token()


def sanitize(text: str) -> str:
    """日志脱敏：Cookie 值、XSRF token、15-22位订单号(保留前6位)、敏感关键字"""
    text = text.replace("\r", " ").replace("\n", " ")
    text = _RE_COOKIE.sub(r"\1***", text)
    text = _RE_XSRF.sub(r"\1***", text)
    text = _RE_ORDER.sub(lambda m: m.group(0)[:6] + "***", text)
    text = _RE_FALLBACK.sub(r"\1***", text)
    return text


_SENSITIVE_KEYS = ("cookie", "token", "secret", "session", "credential", "password")


def sanitize_dict(data) -> object:
    """递归脱敏 dict/list 中的所有 str 值，返回新结构，不修改原数据
    键名含敏感关键字时，值整体掩码（防裸值绕过前缀正则）"""
    if isinstance(data, dict):
        return {k: _sanitize_value(k, v) for k, v in data.items()}
    if isinstance(data, list):
        return [sanitize_dict(v) for v in data]
    if isinstance(data, str):
        return sanitize(data)
    return data


def _sanitize_value(key, value):
    if isinstance(key, str) and key.lower() in _SENSITIVE_KEYS and isinstance(value, str) and value:
        if len(value) <= 8:
            return "***"
        return value[:4] + "***" + value[-4:]
    return sanitize_dict(value)
