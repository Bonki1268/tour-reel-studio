"""Higgsfield webhook 簽章：官方沒有簽章，由我方以 HMAC 簽回呼網址（spec 0012 待決事項 1）。"""

import hashlib
import hmac
from urllib.parse import urlencode

from app.config import Settings

WEBHOOK_PATH = "/webhooks/higgsfield"


def sign(secret: str, ref: str) -> str:
    return hmac.new(secret.encode(), ref.encode(), hashlib.sha256).hexdigest()


def verify(secret: str | None, ref: str | None, sig: str | None) -> bool:
    """以常數時間比較；密鑰、參考值或簽章任何一項缺少都視為無效。"""
    if not secret or not ref or not sig:
        return False
    return hmac.compare_digest(sign(secret, ref), sig)


def _secret(settings: Settings) -> str | None:
    s = settings.higgsfield_webhook_secret
    return s.get_secret_value() if s is not None else None


def callback_url(settings: Settings, ref: str) -> str | None:
    """WEBHOOK_ENABLED、PUBLIC_BASE_URL 與簽章密鑰都有設定時回傳回呼網址，否則 None。"""
    secret = _secret(settings)
    base = settings.public_base_url.strip().rstrip("/")
    if not settings.webhook_enabled or not base or not secret:
        return None
    return f"{base}{WEBHOOK_PATH}?{urlencode({'ref': ref, 'sig': sign(secret, ref)})}"


def verify_request(settings: Settings, ref: str | None, sig: str | None) -> bool:
    return verify(_secret(settings), ref, sig)
