"""Higgsfield webhook 簽章：官方沒有簽章，由我方以 HMAC 簽回呼網址（spec 0012 待決事項 1）。"""

from app.config import Settings


def sign(secret: str, ref: str) -> str:
    raise NotImplementedError


def verify(secret: str | None, ref: str | None, sig: str | None) -> bool:
    raise NotImplementedError


def callback_url(settings: Settings, ref: str) -> str | None:
    """WEBHOOK_ENABLED、PUBLIC_BASE_URL 與簽章密鑰都有設定時回傳回呼網址，否則 None。"""
    raise NotImplementedError
