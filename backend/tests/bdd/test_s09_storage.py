import asyncio
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from app.config import load_settings
from app.storage import keys
from app.storage.objects import ObjectNotFound, S3Storage
from tests.storage_support import PNG_BYTES, s3_cleanup

pytestmark = pytest.mark.S09

scenarios("api/s09_storage.feature")


@pytest.fixture
def ctx() -> Iterator[dict[str, Any]]:
    c: dict[str, Any] = {"keys": []}
    yield c
    s3_cleanup(c["keys"])


@pytest.fixture
def storage() -> S3Storage:
    return S3Storage(load_settings(env_file=None))


def run(coro: Any) -> Any:
    return asyncio.run(coro)


# S09-01


@given("測試用 MinIO 已啟動")
def minio_running(ctx: dict[str, Any], storage: S3Storage) -> None:
    settings = load_settings(env_file=None)
    r = httpx.get(f"{settings.s3_endpoint_url}/minio/health/live", timeout=5)
    assert r.status_code == 200
    ctx["storage"] = storage


@when(parsers.parse('上傳一個 PNG 檔到 "{key}"'))
def upload_png(ctx: dict[str, Any], key: str) -> None:
    ctx["keys"].append(key)
    run(ctx["storage"].put(key, PNG_BYTES, "image/png"))
    ctx["key"] = key


@then("可以讀回相同內容")
def read_back(ctx: dict[str, Any]) -> None:
    storage: S3Storage = ctx["storage"]
    assert run(storage.get(ctx["key"])) == PNG_BYTES
    assert run(storage.exists(ctx["key"])) is True
    missing = ctx["key"] + ".missing"
    assert run(storage.exists(missing)) is False
    with pytest.raises(ObjectNotFound):
        run(storage.get(missing))


# S09-02


@given(parsers.parse('取得 "{key}" 的預簽名上傳網址'))
def presigned_put(ctx: dict[str, Any], storage: S3Storage, key: str) -> None:
    ctx["keys"].append(key)
    ctx.update(storage=storage, key=key, url=run(storage.presign_put(key, 60, "image/jpeg")).url)


@when("以 HTTP PUT 將檔案上傳到該網址")
def http_put(ctx: dict[str, Any]) -> None:
    r = httpx.put(ctx["url"], content=PNG_BYTES, headers={"Content-Type": "image/jpeg"}, timeout=10)
    assert r.status_code == 200, r.text


@then("物件存在於儲存中")
def object_exists(ctx: dict[str, Any]) -> None:
    storage: S3Storage = ctx["storage"]
    assert run(storage.exists(ctx["key"])) is True
    assert run(storage.get(ctx["key"])) == PNG_BYTES


# S09-03


@when(parsers.parse('產生影片 "{video_id}" 第 {shot_no:d} 鏡第 {take:d} 次版本的關鍵幀路徑'))
def keyframe_path(ctx: dict[str, Any], video_id: str, shot_no: int, take: int) -> None:
    ctx["path"] = keys.keyframe(video_id, shot_no, take)


@then(parsers.parse('路徑為 "{expected}"'))
def path_is(ctx: dict[str, Any], expected: str) -> None:
    assert ctx["path"] == expected


# S09-04


@given(parsers.parse("取得有效期 {seconds:d} 秒的預簽名下載網址"))
def short_presigned_get(ctx: dict[str, Any], storage: S3Storage, seconds: int) -> None:
    key = "videos/v-s0904/renders/r1.mp4"
    ctx["keys"].append(key)
    run(storage.put(key, b"mp4-bytes", "video/mp4"))
    url = run(storage.presign_get(key, seconds)).url
    fresh = httpx.get(url, timeout=10)
    assert (fresh.status_code, fresh.content) == (200, b"mp4-bytes")  # 有效期內可下載
    ctx["url"] = url


@when(parsers.parse("等待 {seconds:d} 秒後下載"))
def wait_and_download(ctx: dict[str, Any], seconds: int) -> None:
    time.sleep(seconds)
    ctx["response"] = httpx.get(ctx["url"], timeout=10)


@then("下載被拒絕")
def download_rejected(ctx: dict[str, Any]) -> None:
    assert ctx["response"].status_code == 403
