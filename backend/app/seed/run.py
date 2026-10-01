"""Demo 種子腳本（spec 0017）：python -m app.seed.run [--demo-dir] [--cache-dir] [--refresh-firecrawl]。

以自然鍵確保冪等：專案 ID 由專案名稱以 UUIDv5 產生；角色版本與實景照以檔案內容雜湊判斷是否已存在。
"""

import argparse
import asyncio
import io
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from app.config import REPO_ROOT, load_settings
from app.domain.ports import (
    BrandProfile,
    Character,
    CharacterVersion,
    Project,
    Repositories,
    ScenePhoto,
    Storage,
)
from app.domain.video import utc_now
from app.seed import firecrawl
from app.seed.assets import SCENE_SIZE, content_id, prepare_cutout, prepare_scene
from app.seed.firecrawl import BrandPatch, brand_from_firecrawl, domain_of, load_cache
from app.seed.schema import SeedDemo, SeedError, validate_dir
from app.storage import keys

DEFAULT_DEMO_DIR = REPO_ROOT / "seed" / "demo"
DEFAULT_CACHE_DIR = REPO_ROOT / "seed" / "cache"
ID_PREFIX = "tour-reel-studio:"


@dataclass
class SeedResult:
    project_id: str
    created: dict[str, int] = field(default_factory=dict)
    reused: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    refresh_failed: bool = False


def project_id_for(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, ID_PREFIX + name))


def _stable_id(*parts: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, ID_PREFIX + ":".join(parts)))


def _to_png(data: bytes) -> bytes:
    with Image.open(io.BytesIO(data)) as image:
        if image.format == "PNG":
            return data
        buf = io.BytesIO()
        image.save(buf, "PNG")
        return buf.getvalue()


async def _put_if_changed(storage: Storage, key: str, data: bytes, content_type: str) -> None:
    if await storage.exists(key) and await storage.get(key) == data:
        return
    await storage.put(key, data, content_type)


async def _load_patch(demo: SeedDemo, cache_dir: Path, result: SeedResult, refresh: bool,
                      api_key: str | None) -> tuple[BrandPatch, dict[str, Any] | None]:
    """官網擷取：只讀快取；refresh 時先嘗試更新快取，失敗則沿用舊快取。"""
    if not demo.website:
        result.warnings.append("demo.json 沒有 website，未使用官網擷取快取，以 demo.json 為準")
        return BrandPatch(), None
    domain = domain_of(demo.website)
    if refresh:
        if not api_key:
            result.refresh_failed = True
            result.warnings.append("未設定 FIRECRAWL_API_KEY，無法更新官網擷取快取")
        elif not await firecrawl.refresh(cache_dir, demo.website, api_key):
            result.refresh_failed = True
            result.warnings.append(f"Firecrawl 擷取 {domain} 失敗，沿用舊快取")
    cache = load_cache(cache_dir, domain)
    if cache is None:
        result.warnings.append(f"沒有 {domain} 的官網擷取快取，以 demo.json 為準")
        return BrandPatch(), None
    source = {"domain": domain, "fetched_at": cache.get("fetched_at"), "source": cache.get("source")}
    return brand_from_firecrawl(cache), source


def _brand(project_id: str, demo: SeedDemo, patch: BrandPatch, firecrawl_source: dict[str, Any] | None,
           logo_key: str | None) -> BrandProfile:
    """demo.json 有明確值者優先，缺少時由官網擷取快取補上。"""
    return BrandProfile(
        project_id=project_id,
        visual={
            "colors": demo.colors or patch.colors,
            "fonts": patch.fonts,
            "logo": {"key": logo_key, "url": patch.logo_url},
        },
        selling_points=list(demo.selling_points),
        tone=demo.tone,
        info={
            "name": demo.name,
            "address": demo.address,
            "booking_url": demo.booking_url or patch.booking_url,
            "website": demo.website,
        },
        sources={"demo_json": "demo.json", "firecrawl": firecrawl_source},
        confirmed_at=utc_now(),
    )


async def _seed_character(demo_dir: Path, demo: SeedDemo, project_id: str, repos: Repositories,
                          storage: Storage, result: SeedResult) -> None:
    spec = demo.character
    board_raw = (demo_dir / spec.identity_board).read_bytes()
    cutout_raw = (demo_dir / spec.cutout).read_bytes()
    char_id = _stable_id(project_id, "character", spec.name)
    version_id = _stable_id(project_id, "character", spec.name, content_id(board_raw), content_id(cutout_raw))

    versions = await repos.characters.versions(project_id)
    if any(v.id == version_id for v in versions):
        result.reused["character_versions"] += 1
        return
    mine = [v for v in versions if v.character_id == char_id]
    number = max((v.version for v in mine), default=0) + 1
    version = CharacterVersion(
        id=version_id, character_id=char_id, version=number, status="locked",
        identity_board_key=keys.identity_board(project_id, char_id, number),
        cutout_key=keys.cutout(project_id, char_id, number),
        anchor_card={"anchor_zh": spec.anchor_zh, "anchor_en": spec.anchor_en},
    )
    assert version.identity_board_key and version.cutout_key
    await storage.put(version.identity_board_key, _to_png(board_raw), "image/png")
    await storage.put(version.cutout_key, prepare_cutout(cutout_raw), "image/png")
    if mine:
        await repos.characters.add_version(version, lock=True)
    else:
        await repos.characters.add(Character(char_id, project_id, spec.name, version_id), [version])
    result.created["character_versions"] += 1


async def _seed_scenes(demo_dir: Path, demo: SeedDemo, project_id: str, repos: Repositories,
                       storage: Storage, result: SeedResult) -> None:
    existing = {p.id for p in await repos.scene_photos.list(project_id)}
    for scene in demo.scenes:
        raw = (demo_dir / scene.file).read_bytes()
        # 雜湊包含專案 ID：不同專案使用同一張照片時主鍵不衝突
        photo_id = content_id(project_id.encode() + raw)
        if photo_id in existing:
            result.reused["scene_photos"] += 1
            continue
        key = keys.scene_photo(project_id, photo_id)
        await storage.put(key, prepare_scene(raw), "image/jpeg")
        width, height = SCENE_SIZE
        photo = ScenePhoto(photo_id, project_id, key, width, height, scene.description_zh)
        await repos.scene_photos.add(photo)
        existing.add(photo_id)
        result.created["scene_photos"] += 1


async def seed(
    demo_dir: Path, cache_dir: Path, repos: Repositories, storage: Storage, *,
    refresh: bool = False, api_key: str | None = None,
) -> SeedResult:
    """建立或補齊 Demo 專案；驗證失敗時拋出 SeedError，不寫入任何資料。"""
    demo, problems = validate_dir(demo_dir)
    if demo is None:
        raise SeedError(problems)
    project_id = project_id_for(demo.name)
    counters = ("project", "character_versions", "scene_photos")
    result = SeedResult(project_id, created=dict.fromkeys(counters, 0), reused=dict.fromkeys(counters, 0))

    patch, firecrawl_source = await _load_patch(demo, cache_dir, result, refresh, api_key)
    logo_key = keys.brand_logo(project_id) if demo.logo else None
    brand = _brand(project_id, demo, patch, firecrawl_source, logo_key)
    if await repos.projects.get(project_id) is None:
        await repos.projects.add(Project(project_id, demo.name), brand)
        result.created["project"] += 1
    else:
        await repos.projects.update_brand(brand)
        result.reused["project"] += 1
    if demo.logo and logo_key:
        await _put_if_changed(storage, logo_key, _to_png((demo_dir / demo.logo).read_bytes()), "image/png")

    await _seed_character(demo_dir, demo, project_id, repos, storage, result)
    await _seed_scenes(demo_dir, demo, project_id, repos, storage, result)
    return result


async def _run_with_services(demo_dir: Path, cache_dir: Path, refresh: bool) -> SeedResult:
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.storage.objects import S3Storage
    from app.storage.sql_repos import sql_repositories

    settings = load_settings()
    engine = create_async_engine(settings.database_url)
    try:
        key = settings.firecrawl_api_key.get_secret_value() if settings.firecrawl_api_key else None
        return await seed(demo_dir, cache_dir, sql_repositories(engine), S3Storage(settings),
                          refresh=refresh, api_key=key)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    """結束代碼：0 成功、1 驗證失敗、2 執行錯誤。"""
    parser = argparse.ArgumentParser(prog="python -m app.seed.run", description="建立 Demo 專案種子資料")
    parser.add_argument("--demo-dir", type=Path, default=DEFAULT_DEMO_DIR)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--refresh-firecrawl", action="store_true", help="呼叫 Firecrawl 更新官網擷取快取（會產生費用）"
    )
    args = parser.parse_args(argv)

    _, problems = validate_dir(args.demo_dir)
    if problems:
        print("種子資料驗證失敗：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    try:
        result = asyncio.run(_run_with_services(args.demo_dir, args.cache_dir, args.refresh_firecrawl))
    except SeedError as e:
        print("\n".join(e.problems), file=sys.stderr)
        return 1
    except Exception as e:  # 資料庫或儲存錯誤：重跑即可補齊（冪等）
        print(f"種子腳本執行失敗：{type(e).__name__}：{e}", file=sys.stderr)
        return 2

    for warning in result.warnings:
        print(f"警告：{warning}", file=sys.stderr)
    print(f"Demo 專案 ID：{result.project_id}")
    labels = {"project": "專案", "character_versions": "角色版本", "scene_photos": "實景照"}
    for name, label in labels.items():
        print(f"  {label}：新增 {result.created[name]}，沿用 {result.reused[name]}")
    if result.refresh_failed:
        print("官網擷取快取更新失敗，已沿用舊快取", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
