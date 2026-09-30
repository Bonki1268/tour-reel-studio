"""S05 測試共用的樣本資料與建立輔助函式。"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.domain.cost import JobKind
from app.domain.ids import new_id
from app.domain.ports import (
    BrandProfile,
    GenerationJob,
    Project,
    Repositories,
    Shot,
    ShotTake,
    VideoRecord,
)

# 架構書 §7 的 14 張資料表
SECTION7_TABLES = frozenset({
    "users", "projects", "brand_profiles", "characters", "character_versions", "scene_photos",
    "videos", "plans", "shots", "shot_takes", "generation_jobs", "approvals", "cost_entries", "renders",
})


def sample_project(name: str = "梅子農場") -> tuple[Project, BrandProfile]:
    project = Project(id=new_id(), name=name, output_defaults={"aspect_ratio": "9:16", "duration_s": 15})
    brand = BrandProfile(
        project_id=project.id,
        visual={"colors": ["#6B8E23", "#F5DEB3"], "logo": {"key": "brand/logo.png", "position": "右下"}},
        selling_points=["手工梅子醋", {"title": "親子採果", "season": [3, 4]}],
        tone="溫暖、在地",
        info={"address": "南投縣信義鄉", "hours": {"平日": "09:00-17:00", "假日": None}, "parking": True},
        sources={"visual": "manual", "info": "website"},
        confirmed_at=datetime(2026, 10, 1, 9, 30, tzinfo=UTC),
    )
    return project, brand


def sample_timeline() -> dict[str, Any]:
    return {
        "version": 1,
        "duration_s": 15.0,
        "fps": 24,
        "tracks": [
            {"type": "clip", "shot_no": 1, "start": 0, "end": 5.5, "muted": True},
            {"type": "clip", "shot_no": 2, "start": 5.5, "end": 10.25, "muted": False},
            {"type": "subtitle", "text": "歡迎來到梅子農場", "style": {"size": 48, "bold": True}},
        ],
        "end_card": {"enabled": True, "lines": ["營業時間 09:00-17:00", "南投縣信義鄉"], "cta": None},
    }


def sample_placement() -> dict[str, Any]:
    return {"x": 0.42, "y": 0.8, "scale": 1, "flip": False, "anchor": "bottom-center", "z": [1, 0]}


async def seed_video(repos: Repositories, **fields: Any) -> VideoRecord:
    project, brand = sample_project()
    await repos.projects.add(project, brand)
    record = VideoRecord(id=new_id(), project_id=project.id, mode="quick", topic="梅子季限定", **fields)
    await repos.videos.add(record)
    return record


async def seed_shot(repos: Repositories, shot_no: int = 1, **fields: Any) -> Shot:
    video = await seed_video(repos)
    shot = Shot(id=new_id(), video_id=video.id, shot_no=shot_no, role="hook", duration_s=5.0, **fields)
    await repos.shots.add_shot(shot)
    return shot


async def seed_take(repos: Repositories) -> ShotTake:
    shot = await seed_shot(repos)
    return await repos.shots.add_take(shot.id)


def make_job(shot_take_id: str, idempotency_key: str, **fields: Any) -> GenerationJob:
    values: dict[str, Any] = {
        "id": new_id(),
        "shot_take_id": shot_take_id,
        "idempotency_key": idempotency_key,
        "kind": JobKind.KEYFRAME,
        "provider": "higgsfield",
        "model": "img-model-a",
        "input_hash": "abc",
        "attempt": 1,
        "input_snapshot": {"prompt": "梅子園晨光", "seed": 7},
        "est_cost": Decimal("1.5"),
    }
    values.update(fields)
    return GenerationJob(**values)


def assert_same_json(actual: Any, expected: Any, path: str = "$") -> None:
    """內容相等，且每個值的 Python 型別相同（例如 1 與 1.0、True 與 1 視為不同）。"""
    assert type(actual) is type(expected), f"{path}：型別 {type(actual).__name__} ≠ {type(expected).__name__}"
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys(), f"{path}：鍵不同 {sorted(actual)} ≠ {sorted(expected)}"
        for k in expected:
            assert_same_json(actual[k], expected[k], f"{path}.{k}")
    elif isinstance(expected, list):
        assert len(actual) == len(expected), f"{path}：長度 {len(actual)} ≠ {len(expected)}"
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            assert_same_json(a, e, f"{path}[{i}]")
    else:
        assert actual == expected, f"{path}：{actual!r} ≠ {expected!r}"
