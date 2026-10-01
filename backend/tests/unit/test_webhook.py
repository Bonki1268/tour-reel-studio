"""Higgsfield webhook 簽章（spec 0012 R-005）。"""

from typing import Any

import pytest
from pydantic import SecretStr

from app.api.main import create_app
from app.providers.webhook import callback_url, sign, verify
from tests.api_support import ApiEnv
from tests.higgsfield_support import WEBHOOK_SECRET, hf_settings

pytestmark = pytest.mark.S12


def test_r005_sign_is_hmac_hex() -> None:
    sig = sign(WEBHOOK_SECRET, "ref-1")
    assert len(sig) == 64 and int(sig, 16) >= 0
    assert sig == sign(WEBHOOK_SECRET, "ref-1")
    assert sig != sign(WEBHOOK_SECRET, "ref-2")
    assert sig != sign("other-secret", "ref-1")


@pytest.mark.parametrize(
    ("ref", "sig", "ok"),
    [
        ("ref-1", "valid", True),
        ("ref-1", "0" * 64, False),
        ("ref-1", None, False),
        ("ref-1", "", False),
        (None, "valid", False),
        ("ref-2", "valid", False),  # 參考值被竄改
    ],
)
def test_r005_verify_signature(ref: str | None, sig: str | None, ok: bool) -> None:
    if sig == "valid":
        sig = sign(WEBHOOK_SECRET, "ref-1")
    assert verify(WEBHOOK_SECRET, ref, sig) is ok


@pytest.mark.parametrize("secret", [None, ""])
def test_r005_no_secret_rejects_all(secret: str | None) -> None:
    assert verify(secret, "ref-1", sign(WEBHOOK_SECRET, "ref-1")) is False


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {
                "webhook_enabled": True,
                "public_base_url": "https://trs.test/",
                "higgsfield_webhook_secret": "s",
            },
            True,
        ),
        (
            {
                "webhook_enabled": False,
                "public_base_url": "https://trs.test",
                "higgsfield_webhook_secret": "s",
            },
            False,
        ),
        ({"webhook_enabled": True, "public_base_url": "", "higgsfield_webhook_secret": "s"}, False),
        ({"webhook_enabled": True, "public_base_url": "https://trs.test"}, False),
    ],
)
def test_r005_callback_url_requires_all_settings(overrides: dict[str, Any], expected: bool) -> None:
    url = callback_url(hf_settings(**overrides), "ref-1")
    if expected:
        assert url == f"https://trs.test/webhooks/higgsfield?ref=ref-1&sig={sign('s', 'ref-1')}"
    else:
        assert url is None


def _env(secret: str | None) -> ApiEnv:
    env = ApiEnv()
    services = env.services
    services.settings = services.settings.model_copy(
        update={"higgsfield_webhook_secret": SecretStr(secret) if secret else None}
    )
    env._app = create_app(services.settings, services)
    return env


async def test_r005_valid_signature_accepted() -> None:
    env = _env(WEBHOOK_SECRET)
    r = await env.request(
        "POST",
        "/webhooks/higgsfield",
        params={"ref": "ref-1", "sig": sign(WEBHOOK_SECRET, "ref-1")},
        json={"request_id": "r", "status": "completed", "error": None, "payload": None},
    )
    assert r.status_code == 202
    assert r.json() == {"accepted": True}


async def test_r005_rejects_when_secret_not_configured() -> None:
    env = _env(None)
    r = await env.request(
        "POST", "/webhooks/higgsfield", params={"ref": "ref-1", "sig": sign(WEBHOOK_SECRET, "ref-1")}, json={}
    )
    assert r.status_code == 401
    assert r.json()["code"] == "invalid_signature"
