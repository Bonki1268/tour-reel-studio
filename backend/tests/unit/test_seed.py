import asyncio
import io
import json
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from PIL import Image

from app.seed import run as seed_run
from app.seed.assets import content_id, has_transparent_background, prepare_cutout, prepare_scene
from app.seed.firecrawl import FIRECRAWL_SCRAPE_URL, brand_from_firecrawl, domain_of, load_cache, refresh
from app.seed.run import project_id_for, seed
from app.seed.schema import SeedError, validate_dir
from app.storage.memory_repos import memory_repositories
from app.storage.objects import MemoryStorage
from tests.seed_support import cache_payload, cutout_png, write_cache, write_demo

pytestmark = pytest.mark.S17

NAME = "古堡 1624 咖啡館"
DOMAIN = "zeelandia-cafe.example.com"


def run(coro: Any) -> Any:
    return asyncio.run(coro)


# R-007 種子 JSON 驗證


def test_r007_valid_demo_dir_has_no_problems(tmp_path: Path) -> None:
    write_demo(tmp_path, NAME)
    demo, problems = validate_dir(tmp_path)
    assert problems == []
    assert demo is not None and demo.name == NAME and len(demo.scenes) == 3


def test_r007_lists_every_problem(tmp_path: Path) -> None:
    data = write_demo(tmp_path, NAME, n_scenes=2)
    del data["name"]
    (tmp_path / "demo.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "scene-2.jpg").unlink()
    (tmp_path / "character_cutout.png").write_bytes(cutout_png(transparent=False))

    demo, problems = validate_dir(tmp_path)

    text = "\n".join(problems)
    assert demo is None
    assert len(problems) >= 4
    assert "name" in text
    assert "實景照" in text and "2" in text
    assert "scene-2.jpg" in text
    assert "character_cutout.png" in text and "透明" in text


def test_r007_more_than_five_scenes_is_a_problem(tmp_path: Path) -> None:
    write_demo(tmp_path, NAME, n_scenes=6)
    demo, problems = validate_dir(tmp_path)
    assert demo is None
    assert any("實景照" in p and "6" in p for p in problems)


def test_r007_missing_demo_json_is_a_problem(tmp_path: Path) -> None:
    demo, problems = validate_dir(tmp_path)
    assert demo is None and any("demo.json" in p for p in problems)


def test_r007_invalid_seed_writes_nothing(tmp_path: Path) -> None:
    write_demo(tmp_path / "demo", NAME, n_scenes=2)
    repos, storage = memory_repositories(), MemoryStorage()

    with pytest.raises(SeedError) as err:
        run(seed(tmp_path / "demo", tmp_path / "cache", repos, storage))

    assert err.value.problems
    assert run(repos.projects.get(project_id_for(NAME))) is None
    assert storage._objects == {}


def test_r007_main_returns_1_on_validation_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_demo(tmp_path / "demo", NAME, n_scenes=2)
    code = seed_run.main(["--demo-dir", str(tmp_path / "demo"), "--cache-dir", str(tmp_path / "cache")])
    assert code == 1
    assert "實景照" in capsys.readouterr().err


# R-003 實景照前處理


def _exif_rotated_photo() -> bytes:
    """4284×5712 直式照片，以橫式儲存加 EXIF Orientation=6；上緣黃色、左右邊 500px 為紅／藍、中間綠。"""
    upright = Image.new("RGB", (4284, 5712), (0, 160, 0))
    upright.paste((255, 0, 0), (0, 0, 500, 5712))
    upright.paste((0, 0, 255), (4284 - 500, 0, 4284, 5712))
    upright.paste((255, 220, 0), (500, 0, 4284 - 500, 300))
    stored = upright.rotate(90, expand=True)  # 5712×4284；Orientation 6 會順時針轉回
    exif = Image.Exif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    stored.save(buf, "JPEG", quality=90, exif=exif)
    return buf.getvalue()


def _near(pixel: Any, color: tuple[int, int, int], tol: int = 40) -> bool:
    return all(abs(int(a) - b) <= tol for a, b in zip(pixel[:3], color, strict=True))


def test_r003_prepare_scene_rotates_and_center_crops() -> None:
    out = Image.open(io.BytesIO(prepare_scene(_exif_rotated_photo())))
    assert out.format == "JPEG"
    assert out.size == (1080, 1920)
    # 置中裁切：左右邊的紅／藍被裁掉，兩側邊緣是綠色
    assert _near(out.getpixel((2, 960)), (0, 160, 0))
    assert _near(out.getpixel((1077, 960)), (0, 160, 0))
    # 已轉正：黃色在上緣，不在側邊
    assert _near(out.getpixel((540, 20)), (255, 220, 0))
    assert _near(out.getpixel((540, 1900)), (0, 160, 0))


def test_r003_prepare_scene_landscape_is_center_cropped_to_portrait() -> None:
    image = Image.new("RGB", (1600, 900), (0, 160, 0))
    image.paste((255, 0, 0), (0, 0, 200, 900))
    buf = io.BytesIO()
    image.save(buf, "PNG")
    out = Image.open(io.BytesIO(prepare_scene(buf.getvalue())))
    assert out.size == (1080, 1920) and out.mode == "RGB"
    assert _near(out.getpixel((2, 960)), (0, 160, 0))


def test_r003_content_id_is_stable_hex() -> None:
    assert content_id(b"abc") == content_id(b"abc")
    assert content_id(b"abc") != content_id(b"abd")
    assert len(content_id(b"abc")) == 16 and int(content_id(b"abc"), 16) >= 0


# R-006 去背圖


def test_r006_prepare_cutout_trims_bottom_and_keeps_corners_transparent() -> None:
    out_bytes = prepare_cutout(cutout_png(bottom_margin=40))
    out = Image.open(io.BytesIO(out_bytes))
    assert out.format == "PNG" and out.mode == "RGBA"
    assert out.size == (300, 560)
    bbox = out.getchannel("A").getbbox()
    assert bbox is not None and bbox[3] == out.height
    assert bbox[1] == 30 and bbox[0] == 60  # 上、左透明邊保留
    assert has_transparent_background(out_bytes)


def test_r006_has_transparent_background_rejects_opaque() -> None:
    assert has_transparent_background(cutout_png())
    assert not has_transparent_background(cutout_png(transparent=False))
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, "PNG")
    assert not has_transparent_background(buf.getvalue())


# R-005 官網擷取


def test_r005_firecrawl_branding_to_brand() -> None:
    patch = brand_from_firecrawl(cache_payload())
    assert patch.colors == ["#1F4E8B", "#F2E3C6", "#C9A227"]
    assert patch.logo_url == "https://zeelandia-cafe.example.com/logo.svg"
    assert patch.fonts == ["Noto Serif TC", "Inter"]
    assert patch.booking_url == "https://cache.example.com/booking"


def test_r005_firecrawl_partial_branding() -> None:
    patch = brand_from_firecrawl({"branding": {"colors": {"primary": "#112233"}}})
    assert patch.colors == ["#112233"]
    assert patch.logo_url is None and patch.fonts == [] and patch.booking_url is None
    assert brand_from_firecrawl({}).colors == []


def test_r005_domain_and_cache(tmp_path: Path) -> None:
    assert domain_of("https://www.Zeelandia-Cafe.example.com/menu") == DOMAIN
    assert load_cache(tmp_path, DOMAIN) is None
    write_cache(tmp_path, DOMAIN)
    assert load_cache(tmp_path, DOMAIN) == cache_payload()


@respx.mock
def test_r005_refresh_failure_keeps_cache(tmp_path: Path) -> None:
    path = write_cache(tmp_path, DOMAIN)
    before = path.read_bytes()
    respx.post(FIRECRAWL_SCRAPE_URL).mock(side_effect=httpx.ConnectError("offline"))

    ok = run(refresh(tmp_path, "https://zeelandia-cafe.example.com", "fc-test-key"))

    assert ok is False
    assert path.read_bytes() == before


@respx.mock
def test_r005_refresh_server_error_keeps_cache(tmp_path: Path) -> None:
    path = write_cache(tmp_path, DOMAIN)
    before = path.read_bytes()
    respx.post(FIRECRAWL_SCRAPE_URL).mock(return_value=httpx.Response(500, json={"success": False}))
    assert run(refresh(tmp_path, "https://zeelandia-cafe.example.com", "fc-test-key")) is False
    assert path.read_bytes() == before


@respx.mock
def test_r005_refresh_success_writes_cache_without_key(tmp_path: Path) -> None:
    route = respx.post(FIRECRAWL_SCRAPE_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "data": {
            "branding": {"colors": {"primary": "#000000"}}, "metadata": {"title": "t"},
        }})
    )

    ok = run(refresh(tmp_path, "https://zeelandia-cafe.example.com", "fc-test-key"))

    assert ok is True
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer fc-test-key"
    assert json.loads(request.content)["url"] == "https://zeelandia-cafe.example.com"
    raw = (tmp_path / f"firecrawl-{DOMAIN}.json").read_text(encoding="utf-8")
    assert "fc-test-key" not in raw
    cached = json.loads(raw)
    assert cached["source"] == "firecrawl" and cached["fetched_at"]
    assert cached["branding"] == {"colors": {"primary": "#000000"}}


@respx.mock
def test_r005_seed_without_refresh_never_calls_network(tmp_path: Path) -> None:
    route = respx.post(FIRECRAWL_SCRAPE_URL).mock(return_value=httpx.Response(200, json={}))
    write_demo(tmp_path / "demo", NAME)
    run(seed(tmp_path / "demo", tmp_path / "cache", memory_repositories(), MemoryStorage(), api_key="k"))
    assert not route.called


def test_r005_no_cache_uses_demo_json_and_warns(tmp_path: Path) -> None:
    write_demo(tmp_path / "demo", NAME)
    repos = memory_repositories()

    result = run(seed(tmp_path / "demo", tmp_path / "cache", repos, MemoryStorage()))

    assert any("快取" in w for w in result.warnings)
    _, brand = run(repos.projects.get(result.project_id))
    assert brand.visual["colors"] == ["#8B2E1F"]
    assert brand.info["booking_url"] == "https://zeelandia-cafe.example.com/booking"


def test_r005_cache_fills_missing_values_and_demo_json_wins(tmp_path: Path) -> None:
    write_demo(tmp_path / "demo", NAME, colors=[], booking_url=None)
    write_cache(tmp_path / "cache", DOMAIN)
    repos = memory_repositories()

    result = run(seed(tmp_path / "demo", tmp_path / "cache", repos, MemoryStorage()))

    _, brand = run(repos.projects.get(result.project_id))
    assert brand.visual["colors"][0] == "#1F4E8B"
    assert brand.visual["fonts"] == ["Noto Serif TC", "Inter"]
    assert brand.visual["logo"]["url"] == "https://zeelandia-cafe.example.com/logo.svg"
    assert brand.info["booking_url"] == "https://cache.example.com/booking"
    assert brand.sources["firecrawl"]["source"] == "manual"

    write_demo(tmp_path / "demo2", NAME)  # demo.json 有明確主色與訂位網址
    run(seed(tmp_path / "demo2", tmp_path / "cache", repos, MemoryStorage()))
    _, brand = run(repos.projects.get(result.project_id))
    assert brand.visual["colors"] == ["#8B2E1F"]
    assert brand.info["booking_url"] == "https://zeelandia-cafe.example.com/booking"


# R-001／R-002／R-004 種子流程（記憶體 repository）


def test_r001_project_id_is_stable() -> None:
    expected = str(uuid.uuid5(uuid.NAMESPACE_URL, "tour-reel-studio:" + NAME))
    assert project_id_for(NAME) == expected
    assert project_id_for(NAME + "2") != expected


def test_r001_seed_creates_confirmed_project(tmp_path: Path) -> None:
    write_demo(tmp_path / "demo", NAME)
    repos, storage = memory_repositories(), MemoryStorage()

    result = run(seed(tmp_path / "demo", tmp_path / "cache", repos, storage))

    assert result.project_id == project_id_for(NAME)
    project, brand = run(repos.projects.get(result.project_id))
    assert project.name == NAME and brand.confirmed_at is not None
    assert brand.tone == "歷史趣味、輕鬆親切" and brand.selling_points == ["戶外露天座位", "古堡拿鐵"]
    assert brand.info["address"] == "台南市安平區 安平古堡園區內"
    assert run(storage.exists(brand.visual["logo"]["key"]))
    version = run(repos.characters.locked_version(result.project_id))
    assert version.status == "locked" and version.anchor_card["anchor_en"]
    photos = run(repos.scene_photos.list(result.project_id))
    assert [p.description for p in photos] == ["實景 1", "實景 2", "實景 3"]
    assert all((p.width, p.height) == (1080, 1920) for p in photos)


def test_r004_rerun_and_changed_assets(tmp_path: Path) -> None:
    demo = tmp_path / "demo"
    write_demo(demo, NAME)
    repos, storage = memory_repositories(), MemoryStorage()
    first = run(seed(demo, tmp_path / "cache", repos, storage))
    v1 = run(repos.characters.locked_version(first.project_id))

    second = run(seed(demo, tmp_path / "cache", repos, storage))
    assert second.created == {"project": 0, "character_versions": 0, "scene_photos": 0}
    assert len(run(repos.scene_photos.list(first.project_id))) == 3
    assert len(run(repos.characters.versions(first.project_id))) == 1

    (demo / "character_cutout.png").write_bytes(cutout_png(bottom_margin=10))
    third = run(seed(demo, tmp_path / "cache", repos, storage))
    versions = run(repos.characters.versions(first.project_id))
    locked = run(repos.characters.locked_version(first.project_id))
    assert third.created["character_versions"] == 1
    assert sorted(v.version for v in versions) == [1, 2]
    assert locked.version == 2 and locked.id != v1.id
