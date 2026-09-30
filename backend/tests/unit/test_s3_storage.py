"""儲存實作（spec 0009 R-001、R-002、R-005）。不需要連線：boto3 產生預簽名網址不會發出請求。"""

from datetime import UTC, datetime, timedelta

import pytest

from app.api.services import build_services
from app.config import REPO_ROOT, Settings
from app.storage.objects import MemoryStorage, ObjectNotFound, S3Storage

pytestmark = pytest.mark.S09


async def test_r001_memory_get_missing_raises_object_not_found() -> None:
    storage = MemoryStorage()
    with pytest.raises(ObjectNotFound):
        await storage.get("projects/p1/scenes/none.jpg")
    with pytest.raises(KeyError):  # 既有呼叫端以 KeyError 捕捉仍然有效
        await storage.get("projects/p1/scenes/none.jpg")


async def test_r002_memory_presign_put() -> None:
    storage = MemoryStorage()
    before = datetime.now(UTC)

    url = await storage.presign_put("projects/p1/scenes/ph_02.jpg", 60, "image/jpeg")

    assert "projects/p1/scenes/ph_02.jpg" in url.url
    assert before + timedelta(seconds=59) <= url.expires_at <= datetime.now(UTC) + timedelta(seconds=60)


async def test_r005_presign_uses_public_endpoint() -> None:
    storage = S3Storage(Settings(s3_endpoint_url="http://minio:9000",
                                 s3_public_endpoint_url="http://localhost:59000"))

    get = await storage.presign_get("videos/v1/renders/r1.mp4", 600)
    put = await storage.presign_put("projects/p1/scenes/ph_01.jpg", 600, "image/jpeg")

    assert get.url.startswith("http://localhost:59000/trs-test/videos/v1/renders/r1.mp4?")
    assert put.url.startswith("http://localhost:59000/trs-test/projects/p1/scenes/ph_01.jpg?")
    assert "trs-secret-123" not in get.url
    assert timedelta(seconds=590) < get.expires_at - datetime.now(UTC) <= timedelta(seconds=600)


async def test_r005_presign_defaults_to_endpoint() -> None:
    storage = S3Storage(Settings(s3_endpoint_url="http://minio:9000"))

    url = await storage.presign_get("videos/v1/renders/r1.mp4", 60)

    assert url.url.startswith("http://minio:9000/trs-test/")


def test_r005_build_services_uses_s3() -> None:
    settings = Settings(cost_table=REPO_ROOT / "config" / "cost_table.example.json", creative_engine="fake")

    services = build_services(settings)

    assert isinstance(services.storage, S3Storage)
    assert services.orchestrator.deps.storage is services.storage
