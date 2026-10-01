"""S12 測試共用：以 respx 模擬 Higgsfield API、記憶體儲存與測試設定。"""

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import respx
from pydantic import SecretStr

from app.config import Settings
from app.providers.base import ProviderRequest
from app.providers.higgsfield import HiggsfieldProvider
from app.storage.objects import MemoryStorage

BASE = "https://hf.test"
KEY_ID = "hfkid-7d1e0c"
KEY_SECRET = "hfsec-93ab5f2c1d"
API_KEY = f"{KEY_ID}:{KEY_SECRET}"
IMAGE_MODEL = "xai/grok-imagine-image-2.0"
VIDEO_MODEL = "bytedance/seedance-2.5/image-to-video"
WEBHOOK_SECRET = "whsec-test-5a7c"
REQUEST_ID = "3f1c2a9e-0000-4000-8000-000000000001"
RESULT_VIDEO_URL = "https://cdn.hf.test/results/clip.mp4"
RESULT_IMAGE_URL = "https://cdn.hf.test/results/keyframe.png"

KEYFRAME_KEY = "videos/v1/shots/1/take1/keyframe.png"
ROUGH_KEY = "videos/v1/shots/1/take1/rough.png"
MASK_KEY = "videos/v1/shots/1/take1/mask.png"
BOARD_KEY = "projects/p1/characters/c1/v1/identity_board.png"


def hf_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "higgsfield_api_key": SecretStr(API_KEY),
        "higgsfield_base_url": BASE,
        "hf_image_model": IMAGE_MODEL,
        "hf_video_model": VIDEO_MODEL,
        "webhook_enabled": False,
        "generation_poll_interval_s": 1,
    }
    values.update(overrides)
    return Settings(**values)


@dataclass
class HfMock:
    """模擬上傳、送出、查詢與結果下載；記錄每個請求。"""

    router: respx.MockRouter
    uploads: list[bytes] = field(default_factory=list)
    statuses: list[dict[str, Any]] = field(default_factory=list)

    def public_url(self, n: int) -> str:
        return f"https://files.hf.test/upload-{n}.png"

    def install(self) -> None:
        counter = {"n": 0}

        def upload_url(request: httpx.Request) -> httpx.Response:
            counter["n"] += 1
            n = counter["n"]
            return httpx.Response(
                200,
                json={
                    "public_url": self.public_url(n),
                    "upload_url": f"https://upload.hf.test/put-{n}",
                    "upload_headers": {"Content-Type": json.loads(request.content)["content_type"]},
                },
            )

        def put(request: httpx.Request) -> httpx.Response:
            self.uploads.append(request.content)
            return httpx.Response(200)

        def status(request: httpx.Request) -> httpx.Response:
            body = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return httpx.Response(200, json={"request_id": REQUEST_ID, **body})

        self.router.post(f"{BASE}/files/generate-upload-url").mock(side_effect=upload_url)
        self.router.put(url__startswith="https://upload.hf.test/").mock(side_effect=put)
        self.router.post(f"{BASE}/{VIDEO_MODEL}").respond(200, json=_submitted())
        self.router.post(f"{BASE}/{IMAGE_MODEL}").respond(200, json=_submitted())
        self.router.get(f"{BASE}/requests/{REQUEST_ID}/status").mock(side_effect=status)
        self.router.get(RESULT_VIDEO_URL).respond(
            200, content=b"mp4-bytes", headers={"Content-Type": "video/mp4"}
        )
        self.router.get(RESULT_IMAGE_URL).respond(
            200, content=b"png-bytes", headers={"Content-Type": "image/png"}
        )

    def submit_calls(self, model: str) -> list[httpx.Request]:
        return [c.request for c in self.router.calls if c.request.url.path == f"/{model}"]

    def submitted_body(self, model: str) -> dict[str, Any]:
        calls = self.submit_calls(model)
        assert len(calls) == 1, f"{model} 送出 {len(calls)} 次"
        return dict(json.loads(calls[0].content))


def _submitted() -> dict[str, Any]:
    return {
        "status": "queued",
        "request_id": REQUEST_ID,
        "status_url": f"{BASE}/requests/{REQUEST_ID}/status",
        "cancel_url": f"{BASE}/requests/{REQUEST_ID}/cancel",
    }


def hf_mock() -> Iterator[HfMock]:
    with respx.mock(assert_all_called=False) as router:
        mock = HfMock(router)
        mock.install()
        yield mock


async def seeded_storage() -> MemoryStorage:
    storage = MemoryStorage()
    await storage.put(KEYFRAME_KEY, b"keyframe-png", "image/png")
    await storage.put(ROUGH_KEY, b"rough-png", "image/png")
    await storage.put(MASK_KEY, b"mask-png", "image/png")
    await storage.put(BOARD_KEY, b"board-png", "image/png")
    return storage


def provider(storage: MemoryStorage, **settings: Any) -> HiggsfieldProvider:
    return HiggsfieldProvider(hf_settings(**settings), storage)


def i2v_request(key: str = "pik-1") -> ProviderRequest:
    return ProviderRequest(
        VIDEO_MODEL,
        {"shot_no": 1, "keyframe_key": KEYFRAME_KEY, "prompt": "Guide waves", "duration_s": 5.0},
        key,
    )


def compose_request(key: str = "pik-2") -> ProviderRequest:
    return ProviderRequest(
        IMAGE_MODEL,
        {
            "shot_no": 1,
            "base_image_key": ROUGH_KEY,
            "mask_key": MASK_KEY,
            "reference_keys": [BOARD_KEY],
            "prompt": "Keep the background exactly unchanged.",
        },
        key,
    )
