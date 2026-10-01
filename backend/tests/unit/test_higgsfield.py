"""Higgsfield adapter（spec 0012）。"""

import logging
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import httpx
import pytest

from app.providers.base import ProviderError, ProviderJob
from app.providers.higgsfield import (
    RedactSecrets,
    classify,
    compose_args,
    i2v_args,
    map_status,
    parse_cost,
)
from app.providers.webhook import verify
from tests.higgsfield_support import (
    API_KEY,
    BASE,
    IMAGE_MODEL,
    KEY_SECRET,
    REQUEST_ID,
    RESULT_IMAGE_URL,
    RESULT_VIDEO_URL,
    VIDEO_MODEL,
    WEBHOOK_SECRET,
    HfMock,
    compose_request,
    hf_mock,
    i2v_request,
    provider,
    seeded_storage,
)

pytestmark = pytest.mark.S12


@pytest.fixture
def hf() -> Iterator[HfMock]:
    yield from hf_mock()


# R-001


def test_r001_i2v_args_disable_audio() -> None:
    args = i2v_args("https://files/k.png", "Guide waves", 5)
    assert args == {
        "image_url": "https://files/k.png",
        "prompt": "Guide waves",
        "duration": 5,
        "resolution": "720p",
        "output_format": "mp4",
        "generate_audio": False,
    }


@pytest.mark.parametrize(("duration_s", "expected"), [(None, 4), (3.0, 4), (4.0, 4), (5.0, 5), (4.2, 5)])
async def test_r001_duration_rounds_up_with_minimum(
    hf: HfMock, duration_s: float | None, expected: int
) -> None:
    req = i2v_request()
    data = dict(req.input)
    if duration_s is None:
        data.pop("duration_s")
    else:
        data["duration_s"] = duration_s
    p = provider(await seeded_storage())
    await p.image_to_video(type(req)(req.model, data, req.provider_idempotency_key))
    assert hf.submitted_body(VIDEO_MODEL)["duration"] == expected


async def test_r001_sends_idempotency_key(hf: HfMock) -> None:
    p = provider(await seeded_storage())
    await p.image_to_video(i2v_request("idem-123"))
    request = hf.submit_calls(VIDEO_MODEL)[0]
    assert request.headers["Idempotency-Key"] == "idem-123"
    upload = next(c.request for c in hf.router.calls if c.request.url.host == "upload.hf.test")
    assert "Authorization" not in upload.headers  # 上傳網址是第三方預簽名網址，不帶金鑰
    assert upload.headers["Content-Type"] == "image/png"


async def test_r001_webhook_param_only_when_enabled(hf: HfMock) -> None:
    storage = await seeded_storage()
    await provider(storage).image_to_video(i2v_request("pik-a"))
    assert "hf_webhook" not in hf.submit_calls(VIDEO_MODEL)[0].url.params

    await provider(
        storage,
        webhook_enabled=True,
        public_base_url="https://trs.test",
        higgsfield_webhook_secret=WEBHOOK_SECRET,
    ).image_to_video(i2v_request("pik-b"))
    hook = httpx.URL(hf.submit_calls(VIDEO_MODEL)[1].url.params["hf_webhook"])
    assert str(hook).startswith("https://trs.test/webhooks/higgsfield?")
    assert hook.params["ref"] == "pik-b"
    assert verify(WEBHOOK_SECRET, hook.params["ref"], hook.params["sig"])


async def test_r001_missing_keyframe_is_non_retryable(hf: HfMock) -> None:
    p = provider(await seeded_storage())
    req = i2v_request()
    with pytest.raises(ProviderError) as exc:
        await p.image_to_video(type(req)(req.model, {**req.input, "keyframe_key": "nope.png"}, "k"))
    assert exc.value.retryable is False
    assert hf.submit_calls(VIDEO_MODEL) == []


# R-002


def test_r002_compose_args_order_and_ratio() -> None:
    assert compose_args("p", ["https://a", "https://b"]) == {
        "prompt": "p",
        "image_urls": ["https://a", "https://b"],
        "aspect_ratio": "9:16",
        "resolution": "1k",
        "quality": "medium",
    }


async def test_r002_mask_not_uploaded(hf: HfMock) -> None:
    await provider(await seeded_storage()).compose(compose_request())
    assert b"mask-png" not in hf.uploads
    assert len(hf.uploads) == 2


async def test_r002_upload_failure_is_classified(hf: HfMock) -> None:
    hf.router.post(f"{BASE}/files/generate-upload-url").respond(503, json={"detail": "busy"})
    with pytest.raises(ProviderError) as exc:
        await provider(await seeded_storage()).compose(compose_request())
    assert exc.value.retryable is True
    assert hf.submit_calls(IMAGE_MODEL) == []


# R-003


@pytest.mark.parametrize(
    ("status", "state", "retryable"),
    [
        ("queued", "running", None),
        ("in_progress", "running", None),
        ("completed", "succeeded", None),
        ("failed", "failed", False),
        ("nsfw", "failed", False),
        ("canceled", "failed", False),
        ("mystery", "failed", False),
    ],
)
def test_r003_status_mapping(status: str, state: str, retryable: bool | None) -> None:
    result = map_status({"status": status, "video": {"url": RESULT_VIDEO_URL}, "error": "boom"})
    assert result.state == state
    if state == "succeeded":
        assert result.url == RESULT_VIDEO_URL
    if retryable is not None:
        assert result.error is not None and result.error.retryable is retryable


def test_r003_failure_messages() -> None:
    assert "boom" in str(map_status({"status": "failed", "error": "boom"}).error)
    assert "nsfw" in str(map_status({"status": "nsfw"}).error)
    assert "取消" in str(map_status({"status": "canceled"}).error)


def test_r003_image_result_url() -> None:
    result = map_status({"status": "completed", "images": [{"url": RESULT_IMAGE_URL}, {"url": "x"}]})
    assert result.url == RESULT_IMAGE_URL


def test_r003_completed_without_url_fails() -> None:
    result = map_status({"status": "completed", "images": []})
    assert result.state == "failed"
    assert result.error is not None and result.error.retryable is True


@pytest.mark.parametrize(
    ("body", "cost"),
    [
        ({"credits": 1.28}, Decimal("1.28")),
        ({"credits": "2.5"}, Decimal("2.5")),
        ({"cost": 3}, Decimal("3")),
    ],
)
def test_r003_cost_parsed(body: dict[str, Any], cost: Decimal) -> None:
    assert parse_cost(body) == cost
    assert map_status({"status": "completed", "video": {"url": "u"}, **body}).actual_cost == cost


@pytest.mark.parametrize(
    "body", [{}, {"credits": None}, {"credits": "n/a"}, {"credits": True}, {"cost": "nan"}]
)
def test_r003_cost_missing_is_none(body: dict[str, Any]) -> None:
    assert parse_cost(body) is None


async def test_r003_fetch_result_uses_status_endpoint(hf: HfMock) -> None:
    hf.statuses[:] = [{"status": "completed", "images": [{"url": RESULT_IMAGE_URL}]}]
    p = provider(await seeded_storage())
    result = await p.fetch_result(ProviderJob("higgsfield", IMAGE_MODEL, REQUEST_ID))
    assert result.state == "succeeded" and result.url == RESULT_IMAGE_URL
    content, content_type = await p.download(result)
    assert (content, content_type) == (b"png-bytes", "image/png")
    download = next(c.request for c in hf.router.calls if str(c.request.url) == RESULT_IMAGE_URL)
    assert "Authorization" not in download.headers


async def test_r003_status_http_error_is_provider_error(hf: HfMock) -> None:
    hf.router.get(f"{BASE}/requests/{REQUEST_ID}/status").respond(502)
    with pytest.raises(ProviderError) as exc:
        await provider(await seeded_storage()).fetch_result(
            ProviderJob("higgsfield", IMAGE_MODEL, REQUEST_ID)
        )
    assert exc.value.retryable is True


# R-006


@pytest.mark.parametrize(
    ("status", "detail", "retryable"),
    [
        (408, "", True),
        (423, "model blocked", True),
        (429, "", True),
        (500, "", True),
        (502, "", True),
        (503, "not ready", True),
        (400, "invalid prompt", False),
        (400, "Maximum number of concurrent requests (4) has been reached", True),
        (401, "", False),
        (403, "insufficient credits", False),
        (404, "", False),
        (422, "validation failed", False),
    ],
)
def test_r006_classify(status: int, detail: str, retryable: bool) -> None:
    assert classify(status, detail) is retryable


@pytest.mark.parametrize("exc", [httpx.ConnectError("down"), httpx.ReadTimeout("slow")])
async def test_r006_transport_error_retryable(hf: HfMock, exc: Exception) -> None:
    hf.router.post(f"{BASE}/{VIDEO_MODEL}").mock(side_effect=exc)
    with pytest.raises(ProviderError) as err:
        await provider(await seeded_storage()).image_to_video(i2v_request())
    assert err.value.retryable is True


async def test_r006_error_message_excludes_key(hf: HfMock) -> None:
    hf.router.post(f"{BASE}/{VIDEO_MODEL}").respond(
        401, json={"detail": f"bad key {API_KEY} at https://x.test/a?token=abc"}
    )
    with pytest.raises(ProviderError) as exc:
        await provider(await seeded_storage()).image_to_video(i2v_request())
    message = str(exc.value)
    assert "401" in message
    assert API_KEY not in message and KEY_SECRET not in message
    assert "token=abc" not in message


async def test_r006_submit_not_retried_inside_adapter(hf: HfMock) -> None:
    route = hf.router.post(f"{BASE}/{VIDEO_MODEL}").respond(503)
    with pytest.raises(ProviderError):
        await provider(await seeded_storage()).image_to_video(i2v_request())
    assert route.call_count == 1


# R-007


def test_r007_redact_filter_masks_message_and_args() -> None:
    record = logging.LogRecord(
        "httpx", logging.INFO, __file__, 1, "auth %s and %s", (API_KEY, KEY_SECRET), None
    )
    assert RedactSecrets([API_KEY, KEY_SECRET]).filter(record) is True
    message = record.getMessage()
    assert API_KEY not in message and KEY_SECRET not in message
    assert "***" in message
