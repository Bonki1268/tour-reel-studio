"""關鍵幀工作接上 B1 粗合成（spec 0012 R-008）。"""

import io

import pytest
from PIL import Image

from app.providers.composite import build_compose_request
from app.storage import keys
from tests.orchestration_support import OrchEnv

pytestmark = pytest.mark.S12


async def test_r008_keyframe_input_is_compose_request() -> None:
    env = OrchEnv()
    video_id = await env.to_review()
    version = await env.repos.characters.locked_version(env.project_id)
    keyframe_inputs = {
        r.input["shot_no"]: r.input for r in env.provider.submissions if "base_image_key" in r.input
    }
    assert sorted(keyframe_inputs) == [1, 2, 3]
    for shot, take in await env.shots(video_id):
        assert take is not None
        rough_key = keys.rough(video_id, shot.shot_no, take.attempt)
        mask_key = keys.mask(video_id, shot.shot_no, take.attempt)
        expected = build_compose_request(
            rough_key=rough_key,
            mask_key=mask_key,
            identity_board_key=version.identity_board_key,
            keyframe_prompt=shot.prompt["keyframe_prompt"],
        ).to_input()
        assert keyframe_inputs[shot.shot_no] == {"shot_no": shot.shot_no, **expected}
        rough = Image.open(io.BytesIO(await env.storage.get(rough_key)))
        mask = Image.open(io.BytesIO(await env.storage.get(mask_key)))
        assert rough.size == mask.size == (108, 192)
        assert mask.getbbox() is not None


async def test_r008_video_input_carries_duration() -> None:
    env = OrchEnv()
    video_id = await env.to_review()
    durations = {s.shot_no: s.duration_s for s, _ in await env.shots(video_id)}
    video_inputs = [r.input for r in env.provider.submissions if "keyframe_key" in r.input]
    assert {i["shot_no"]: i["duration_s"] for i in video_inputs} == durations


async def test_r008_invalid_placement_fails_without_submit() -> None:
    env = OrchEnv()
    video_id = await env.to_plan_ready()
    await env.approve_first_plan(video_id, placements={2: {"x": 0.5, "y": 0.0, "scale": 0.5, "flip": False}})
    await env.orch.generate(video_id)
    assert all(r.input["shot_no"] != 2 for r in env.provider.submissions)
    assert await env.video_status(video_id) == "needs_attention"
    failed = [e for e in env.bus.events if e.type == "shot_failed"]
    assert [e.shot_no for e in failed] == [2]
    assert await env.shot_done(video_id, 1) and await env.shot_done(video_id, 3)


async def test_r008_missing_cutout_fails_shots_without_submit() -> None:
    env = OrchEnv()
    video_id = await env.to_plan_ready()
    version = await env.repos.characters.locked_version(env.project_id)
    env.storage._objects.pop(version.cutout_key)
    await env.approve_first_plan(video_id)
    await env.orch.generate(video_id)
    assert env.provider.submissions == []
    assert await env.video_status(video_id) == "needs_attention"
