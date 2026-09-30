"""S07 新增的 repository：記憶體版與資料庫版行為一致（spec 0007 R-008／AC-010）。"""

import pytest

from app.domain.ids import new_id
from app.domain.ports import Character, CharacterVersion, Plan, Render, Repositories, ScenePhoto
from app.storage.memory_repos import memory_repositories
from app.storage.sql_repos import sql_repositories
from tests.persistence_data import sample_project, seed_video

pytestmark = pytest.mark.S07


@pytest.fixture(params=["memory", pytest.param("sql", marks=pytest.mark.integration)])
def repos(request: pytest.FixtureRequest) -> Repositories:
    if request.param == "memory":
        return memory_repositories()
    return sql_repositories(request.getfixturevalue("async_engine"))


async def test_r008_plans_roundtrip(repos: Repositories) -> None:
    video = await seed_video(repos)
    plans = [
        Plan(new_id(), video.id, {"title": f"企劃 {n}", "shots": [{"shot_no": 1, "x": 0.5}]}, "fake")
        for n in (1, 2, 3)
    ]
    for plan in plans:
        await repos.plans.add(plan)

    assert await repos.plans.list(video.id) == plans
    assert await repos.plans.get(plans[1].id) == plans[1]
    assert await repos.plans.get(new_id()) is None
    assert await repos.plans.list(new_id()) == []


async def test_r008_character_and_photos_roundtrip(repos: Repositories) -> None:
    project, brand = sample_project()
    await repos.projects.add(project, brand)
    character = Character(new_id(), project.id, "梅子阿伯")
    v1 = CharacterVersion(new_id(), character.id, 1, "draft", anchor_card={"outfit": "舊款"})
    v2 = CharacterVersion(
        new_id(), character.id, 2, "locked", "id_board.png", "cutout.png", {"outfit": "草帽"}, {"pitch": 1.1}
    )
    character.locked_version_id = v2.id
    await repos.characters.add(character, [v1, v2])
    photos = [ScenePhoto(new_id(), project.id, f"scenes/{n}.jpg", 1080, 1920, f"場景 {n}") for n in (1, 2, 3)]
    for photo in photos:
        await repos.scene_photos.add(photo)

    assert await repos.characters.locked_version(project.id) == v2
    assert await repos.characters.locked_version(new_id()) is None
    assert await repos.scene_photos.list(project.id) == photos


async def test_r008_renders_roundtrip(repos: Repositories) -> None:
    video = await seed_video(repos)
    renders = [
        Render(new_id(), video.id, "9:16", f"videos/{video.id}/renders/{n}.mp4", "zh-TW") for n in (1, 2)
    ]
    for render in renders:
        await repos.renders.add(render)

    assert await repos.renders.list(video.id) == renders


async def test_r008_list_shots_sorted_by_shot_no(repos: Repositories) -> None:
    from app.domain.ports import Shot

    video = await seed_video(repos)
    shots = [Shot(new_id(), video.id, n, role="r", duration_s=4.0) for n in (3, 1, 2)]
    for shot in shots:
        await repos.shots.add_shot(shot)

    assert [s.shot_no for s in await repos.shots.list_shots(video.id)] == [1, 2, 3]
