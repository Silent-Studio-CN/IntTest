#!/usr/bin/env python3
"""全局配置 — User-Agent 设置"""

from __future__ import annotations

PRESET_UA = {
    "默认 (不覆盖)": "",
    "Chrome 最新": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Firefox 最新": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) "
        "Gecko/20100101 Firefox/127.0"
    ),
    "Edge 最新": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"
    ),
    "Safari 最新": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.5 Safari/605.1.15"
    ),
}

_current_ua = ""

def set_user_agent(ua: str):
    global _current_ua
    _current_ua = ua

def get_user_agent() -> str:
    return _current_ua

def get_headers() -> dict:
    ua = get_user_agent()
    if ua:
        return {"User-Agent": ua}
    return {}
