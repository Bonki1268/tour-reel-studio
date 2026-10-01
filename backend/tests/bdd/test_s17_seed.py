import asyncio
import io
import uuid
from collections.abc import Coroutine, Iterator
from pathlib import Path
from typing import Any, TypeVar

import boto3
import httpx
import pytest
import respx
from PIL import Image
from pytest_bdd import given, scenarios, then, when
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import load_settings
from app.domain.ports import Repositories
from app.seed.firecrawl import FIRECRAWL_SCRAPE_URL
from app.seed.run import SeedResult, project_id_for, seed
from app.storage.objects import S3Storage
from app.storage.sql_repos import sql_repositories
from tests.conftest import database_url
from tests.seed_support import jpeg, write_cache, write_demo

pytestmark = pytest.mark.S17

scenarios("api/s17_seed.feature")

T = TypeVar("T")


def _s3_client() -> Any:
    s = load_settings(env_file=None)
    return boto3.client(
        "s3", endpoint_url=s.s3_endpoint_url, aws_access_key_id=s.s3_access_key_id,
        aws_secret_access_key=s.s3_secret_access_key.get_secret_value(), region_name=s.s3_region,
    ), s.s3_bucket


def _delete_prefix(prefix: str) -> None:
    client, bucket = _s3_client()
    listed = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    objects = [{"Key": o["Key"]} for o in listed.get("Contents", [])]
    if objects:
        client.delete_objects(Bucket=bucket, Delete={"Objects": objects})


class Env:
    """PostgreSQL＋MinIO；每個測試以獨立的專案名稱（＝獨立的物件前綴）執行，結束時清理。"""

    def __init__(self, tmp_path: Path) -> None:
        self.runner = asyncio.Runner()
        self.engine = create_async_engine(database_url())
        self.repos: Repositories = sql_repositories(self.engine)
        self.storage = S3Storage(load_settings(env_file=None))
        self.name = f"S17 測試咖啡館 {uuid.uuid4().hex[:8]}"
        self.project_id = project_id_for(self.name)
        self.demo_dir = tmp_path / "demo"
        self.cache_dir = tmp_path / "cache"
        self.refresh = False
        self.api_key: str | None = None
        self.results: list[SeedResult] = []
        self.counts: tuple[int, int, int] | None = None
        self.cache_path: Path | None = None
        self.cache_before = b""
        self.cutout: Image.Image | None = None
        self.firecrawl: respx.MockRouter | None = None

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        return self.runner.run(coro)

    def seed(self) -> SeedResult:
        result = self.run(seed(self.demo_dir, self.cache_dir, self.repos, self.storage,
                               refresh=self.refresh, api_key=self.api_key))
        self.results.append(result)
        return result

    def count(self) -> tuple[int, int, int]:
        project = self.run(self.repos.projects.get(self.project_id))
        versions = self.run(self.repos.characters.versions(self.project_id))
        photos = self.run(self.repos.scene_photos.list(self.project_id))
        return int(project is not None), len(versions), len(photos)

    def close(self) -> None:
        if self.firecrawl is not None:
            self.firecrawl.stop()
        _delete_prefix(f"projects/{self.project_id}/")
        self.runner.run(self.engine.dispose())
        self.runner.close()


@pytest.fixture
def env(clean_db: None, tmp_path: Path) -> Iterator[Env]:
    e = Env(tmp_path)
    write_demo(e.demo_dir, e.name)
    yield e
    e.close()


# S17-01


@given("一個已遷移的空資料庫與空的物件儲存")
def empty_env(env: Env) -> None:
    assert env.count() == (0, 0, 0)
    client, bucket = _s3_client()
    assert client.list_objects_v2(Bucket=bucket, Prefix=f"projects/{env.project_id}/").get("KeyCount") == 0


@when("執行種子腳本")
def run_seed(env: Env) -> None:
    env.seed()


@then("存在一個已確認品牌檔案的專案")
def confirmed_project(env: Env) -> None:
    assert env.results[-1].project_id == env.project_id
    found = env.run(env.repos.projects.get(env.project_id))
    assert found is not None
    project, brand = found
    assert project.name == env.name
    assert brand.confirmed_at is not None
    assert brand.tone and brand.selling_points and brand.info["address"]
    assert brand.visual["colors"]
    assert env.run(env.storage.exists(brand.visual["logo"]["key"]))


@then("專案有 1 個已鎖定的角色，含身份板與去背全身圖")
def locked_character(env: Env) -> None:
    versions = env.run(env.repos.characters.versions(env.project_id))
    locked = env.run(env.repos.characters.locked_version(env.project_id))
    assert len(versions) == 1 and locked is not None and locked.status == "locked"
    assert locked.identity_board_key and env.run(env.storage.exists(locked.identity_board_key))
    assert locked.cutout_key and env.run(env.storage.exists(locked.cutout_key))
    assert locked.anchor_card["anchor_zh"] and locked.anchor_card["anchor_en"]


@then("專案有 3 到 5 張附文字描述的實景照")
def scene_photos(env: Env) -> None:
    photos = env.run(env.repos.scene_photos.list(env.project_id))
    assert 3 <= len(photos) <= 5
    for photo in photos:
        assert photo.description.strip()
        assert (photo.width, photo.height) == (1080, 1920)
        image = Image.open(io.BytesIO(env.run(env.storage.get(photo.image_key))))
        assert image.format == "JPEG" and image.size == (1080, 1920)


# S17-02


@given("種子腳本已執行過一次")
def seeded_once(env: Env) -> None:
    env.seed()
    env.counts = env.count()
    assert env.counts == (1, 1, 3)


@then("專案、角色與實景照的數量不變")
def counts_unchanged(env: Env) -> None:
    assert env.count() == env.counts
    assert env.results[-1].created == {"project": 0, "character_versions": 0, "scene_photos": 0}
    # AC-002：替換一張實景照後再執行，實景照多一張且舊的保留
    before = {p.id for p in env.run(env.repos.scene_photos.list(env.project_id))}
    (env.demo_dir / "scene-2.jpg").write_bytes(jpeg((3000, 4000), (10, 20, 30)))
    env.seed()
    after = {p.id for p in env.run(env.repos.scene_photos.list(env.project_id))}
    assert before < after and len(after) == 4
    assert env.count()[:2] == (1, 1)


# S17-03


@given("Firecrawl 無法連線")
def firecrawl_offline(env: Env) -> None:
    # 加上 --refresh-firecrawl 與金鑰，但連線失敗：種子腳本應沿用快取
    env.refresh, env.api_key = True, "fc-test-key"
    env.firecrawl = respx.mock(assert_all_called=True)
    env.firecrawl.post(FIRECRAWL_SCRAPE_URL).mock(side_effect=httpx.ConnectError("offline"))
    env.firecrawl.start()


@given("存在官網擷取結果的快取檔")
def cache_exists(env: Env) -> None:
    write_demo(env.demo_dir, env.name, colors=[], booking_url=None)
    env.cache_path = write_cache(env.cache_dir)
    env.cache_before = env.cache_path.read_bytes()


@then("種子腳本成功完成")
def seed_succeeded(env: Env) -> None:
    result = env.results[-1]
    assert result.refresh_failed is True
    assert env.cache_path is not None and env.cache_path.read_bytes() == env.cache_before
    found = env.run(env.repos.projects.get(env.project_id))
    assert found is not None
    _, brand = found
    assert brand.visual["colors"][0] == "#1F4E8B"
    assert brand.visual["logo"]["url"] == "https://zeelandia-cafe.example.com/logo.svg"
    assert brand.info["booking_url"] == "https://cache.example.com/booking"
    assert env.count() == (1, 1, 3)


# S17-04


@then("角色去背圖為含 alpha 通道的 PNG")
def cutout_is_rgba_png(env: Env) -> None:
    locked = env.run(env.repos.characters.locked_version(env.project_id))
    assert locked is not None and locked.cutout_key
    image = Image.open(io.BytesIO(env.run(env.storage.get(locked.cutout_key))))
    assert image.format == "PNG" and image.mode == "RGBA"
    env.cutout = image


@then("圖片四個角落都是完全透明")
def corners_transparent(env: Env) -> None:
    image = env.cutout
    assert image is not None
    w, h = image.size
    alpha = image.getchannel("A")
    assert [alpha.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))] == [0, 0, 0, 0]
    bbox = alpha.getbbox()
    assert bbox is not None and bbox[3] == h
