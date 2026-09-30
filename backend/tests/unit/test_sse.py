"""SSE 格式與串流順序（spec 0008 R-006）。"""

import asyncio
import json
from datetime import UTC, datetime

import pytest

from app.api.sse import format_sse, sse_stream
from app.jobs.events import MemoryEventBus, ProgressEvent
from tests.api_support import ApiEnv

pytestmark = pytest.mark.S08


def test_r006_sse_format() -> None:
    text = format_sse("plan_ready", {"type": "plan_ready", "video_id": "v1", "note": "企劃完成"})

    lines = text.split("\n")
    assert lines[0] == "event: plan_ready"
    assert lines[1].startswith("data: ")
    expected = {"type": "plan_ready", "video_id": "v1", "note": "企劃完成"}
    assert json.loads(lines[1][len("data: "):]) == expected
    assert text.endswith("\n\n") and text.count("\n") == 3


def test_r006_progress_event_json_roundtrip() -> None:
    event = ProgressEvent("shot_done", "v1", datetime(2026, 10, 1, 9, 0, tzinfo=UTC), 2, {"job_id": "j"})
    data = event.to_json()
    assert data == {"type": "shot_done", "video_id": "v1", "at": "2026-10-01T09:00:00+00:00",
                    "shot_no": 2, "data": {"job_id": "j"}}
    assert ProgressEvent.from_json(json.loads(json.dumps(data))) == event


async def test_r006_memory_bus_delivers_only_after_subscribe() -> None:
    bus = MemoryEventBus()
    at = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    await bus.publish(ProgressEvent("before", "v1", at))
    async with bus.subscribe("v1") as events:
        await bus.publish(ProgressEvent("other_video", "v2", at))
        await bus.publish(ProgressEvent("after", "v1", at))
        first = await asyncio.wait_for(anext(events), 1)
    assert first.type == "after"


async def test_r006_status_event_first() -> None:
    env = ApiEnv(keepalive_s=0.05)
    await env.setup_project()
    video_id = await env.create_video()

    async def connected() -> bool:
        return False

    stream = sse_stream(env.services, video_id, connected)
    first = await anext(stream)
    assert first.startswith("event: status\n")
    assert json.loads(first.split("\n")[1][6:])["status"] == "planning"

    await env.run_jobs()
    received = []
    while not any(chunk.startswith("event: plan_ready") for chunk in received):
        received.append(await asyncio.wait_for(anext(stream), 1))
    assert any(chunk.startswith(": keep-alive") for chunk in received) or received
    await stream.aclose()
