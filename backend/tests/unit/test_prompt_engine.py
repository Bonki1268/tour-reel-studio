"""企劃產生 PromptEngine（spec 0010）。"""

import copy
import json
from typing import Any

import anthropic
import httpx2
import pytest
from pydantic import ValidationError

from app.api.services import build_services
from app.config import REPO_ROOT, ConfigError, Settings
from app.creative.base import PlanDraft, ShotDraft
from app.creative.claude import AnthropicClaudeClient, ClaudeReply
from app.creative.fake import FakeCreativeEngine
from app.creative.prompt_engine import (
    InvalidPlanOutput,
    PlanGenerationError,
    PromptEngine,
    parse_plans,
    validate_plans,
)
from app.creative.schema import PlansOut
from tests.claude_support import (
    TEST_MODEL,
    RecordedClaude,
    engine_settings,
    fixture_json,
    fixture_text,
    plan_context,
)

pytestmark = pytest.mark.S10

FAKE_KEY = "anthropic-test-value-3c9e"


def valid() -> dict[str, Any]:
    return copy.deepcopy(fixture_json("valid_plans.json"))


# R-001：結構驗證


def test_r001_schema_rejects_missing_field() -> None:
    data = valid()
    del data["plans"][0]["shots"][1]["camera_en"]

    with pytest.raises(ValidationError):
        PlansOut.model_validate(data)


def test_r001_schema_rejects_extra_field() -> None:
    data = valid()
    data["plans"][0]["shots"][0]["video_prompt"] = "..."

    with pytest.raises(ValidationError):
        PlansOut.model_validate(data)


@pytest.mark.parametrize("keep", [2, 4])
def test_r001_schema_rejects_shot_count(keep: int) -> None:
    data = valid()
    shots = data["plans"][0]["shots"]
    data["plans"][0]["shots"] = shots[:keep] if keep < 3 else [*shots, copy.deepcopy(shots[-1])]

    with pytest.raises(ValidationError):
        PlansOut.model_validate(data)


def test_r001_schema_rejects_role_order() -> None:
    data = valid()
    shots = data["plans"][0]["shots"]
    shots[0]["role"], shots[1]["role"] = shots[1]["role"], shots[0]["role"]

    with pytest.raises(ValidationError):
        PlansOut.model_validate(data)


@pytest.mark.parametrize(("key", "value"), [("x", 1.2), ("y", -0.1), ("scale", 0), ("scale", 1.5)])
def test_r001_schema_rejects_placement_out_of_range(key: str, value: float) -> None:
    data = valid()
    data["plans"][0]["shots"][0]["placement"][key] = value

    with pytest.raises(ValidationError):
        PlansOut.model_validate(data)


def test_r001_valid_fixture_passes() -> None:
    plans = parse_plans(fixture_text("valid_plans.json"), plan_context())

    assert len(plans.plans) == 3
    assert validate_plans(plans, plan_context()) == []


# R-001：語意驗證


def test_r001_semantic_rejects_duration_sum() -> None:
    plans = PlansOut.model_validate(fixture_json("wrong_duration.json"))

    errors = validate_plans(plans, plan_context())

    assert len(errors) == 1
    assert "12" in errors[0] and "14" in errors[0]


def test_r001_semantic_rejects_unknown_photo() -> None:
    plans = PlansOut.model_validate(fixture_json("missing_photo.json"))

    errors = validate_plans(plans, plan_context())

    assert len(errors) == 1
    assert "ph_99" in errors[0]


def test_r001_semantic_rejects_photo_missing_from_project() -> None:
    plans = PlansOut.model_validate(valid())

    errors = validate_plans(plans, plan_context(photo_count=2))

    assert errors and all("ph_03" in e for e in errors)


@pytest.mark.parametrize("count", [1, 4])
def test_r001_rejects_plan_count(count: int) -> None:
    data = valid()
    data["plans"] = (data["plans"] * 2)[:count]

    with pytest.raises(InvalidPlanOutput):
        parse_plans(json.dumps(data, ensure_ascii=False), plan_context())


def test_r001_parse_rejects_invalid_json() -> None:
    with pytest.raises(InvalidPlanOutput):
        parse_plans(fixture_text("invalid_json.txt"), plan_context())


async def test_r001_plan_draft_keeps_english_fields() -> None:
    engine = PromptEngine(RecordedClaude([fixture_text("valid_plans.json")]), engine_settings())

    plans = await engine.propose_plans(plan_context())

    first = plans[0].shots[0]
    assert first.action_en.startswith("a 60-year-old plum farmer")
    assert first.camera_en == "slow, gentle push-in, moderate distance"
    assert first.placement == {"x": 0.5, "y": 0.9, "scale": 0.5, "flip": False}
    assert plans[0].cta == "私訊預約採梅"


# R-002：重試


async def test_r002_retry_request_contains_previous_error() -> None:
    claude = RecordedClaude([fixture_text("wrong_duration.json"), fixture_text("valid_plans.json")])
    engine = PromptEngine(claude, engine_settings())

    await engine.propose_plans(plan_context())

    first, second = claude.requests
    assert len(first["messages"]) == 1
    assert second["system"] == first["system"]
    assert second["messages"][0] == first["messages"][0]
    assert second["messages"][1] == {"role": "assistant", "content": fixture_text("wrong_duration.json")}
    assert second["messages"][2]["role"] == "user"
    assert "14" in second["messages"][2]["content"]


async def test_r002_schema_sent_to_claude_forbids_extra_properties() -> None:
    claude = RecordedClaude([fixture_text("valid_plans.json")])

    await PromptEngine(claude, engine_settings()).propose_plans(plan_context())

    schema = claude.requests[0]["schema"]
    assert schema["additionalProperties"] is False
    assert "plans" in schema["required"]


# R-003：失敗


async def test_r003_error_reason_describes_last_invalid() -> None:
    claude = RecordedClaude([fixture_text("invalid_json.txt"), fixture_text("missing_photo.json")])

    with pytest.raises(PlanGenerationError) as exc:
        await PromptEngine(claude, engine_settings()).propose_plans(plan_context())

    assert "ph_99" in exc.value.reason
    assert len(claude.requests) == 2


async def test_r003_refusal_raises() -> None:
    claude = RecordedClaude([ClaudeReply(text="", stop_reason="refusal")])

    with pytest.raises(PlanGenerationError) as exc:
        await PromptEngine(claude, engine_settings()).propose_plans(plan_context())

    assert "refusal" in exc.value.reason
    assert len(claude.requests) == 1


async def test_r003_api_error_raises() -> None:
    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    claude = RecordedClaude([error])

    with pytest.raises(PlanGenerationError) as exc:
        await PromptEngine(claude, engine_settings()).propose_plans(plan_context())

    assert "APIConnectionError" in exc.value.reason
    assert len(claude.requests) == 1


async def test_r003_truncated_output_is_invalid() -> None:
    claude = RecordedClaude([ClaudeReply(text='{"plans": [', stop_reason="max_tokens"),
                             fixture_text("valid_plans.json")])

    plans = await PromptEngine(claude, engine_settings()).propose_plans(plan_context())

    assert len(plans) == 3
    assert len(claude.requests) == 2


# R-004：提示詞


def test_r004_prompt_lists_photos_with_id_and_description() -> None:
    engine = PromptEngine(RecordedClaude([]), engine_settings())
    ctx = plan_context()

    system, user = engine.build_prompt(ctx)

    for photo in ctx.scene_photos:
        assert f"- {photo.id}：{photo.description}" in user
    assert "清晨採梅體驗" in user
    assert "親手採青梅" in user and "古法梅子醋" in user
    assert "南投縣信義鄉" in user
    assert "hook" in system and "feature" in system and "cta" in system
    assert "12 秒" in system


def test_r004_prompt_never_contains_api_key() -> None:
    settings = engine_settings(anthropic_api_key=FAKE_KEY)

    system, user = PromptEngine(RecordedClaude([]), settings).build_prompt(plan_context())

    assert FAKE_KEY not in system + user


# R-005：生成提示詞


async def test_r005_anchor_falls_back_to_key_values() -> None:
    ctx = plan_context(anchor_card={"name": "梅子阿伯", "outfit": "藍色工作服、草帽"})
    shot = ShotDraft(shot_no=1, role="hook", duration_s=4, scene_photo_id="ph_01",
                     placement={"x": 0.5, "y": 0.9, "scale": 0.5, "flip": False},
                     action="揮手", action_en="he waves", camera="推進", camera_en="slow push-in")
    plan = PlanDraft(title="t", concept="c", tone="親切台味", shots=[shot])

    (prompt,) = await PromptEngine(RecordedClaude([]), engine_settings()).build_shot_prompts(plan, ctx)

    assert "name: 梅子阿伯" in prompt.video_prompt and "outfit: 藍色工作服、草帽" in prompt.video_prompt
    assert "梅園入口" in prompt.keyframe_prompt
    assert "Camera: slow push-in" in prompt.video_prompt


# R-006：設定


def test_r006_missing_model_is_config_error() -> None:
    with pytest.raises(ConfigError) as exc:
        PromptEngine(RecordedClaude([]), Settings(claude_model="  "))

    assert exc.value.missing == ("CLAUDE_MODEL",)


@pytest.mark.parametrize(("engine_name", "engine_type"),
                         [("prompt", PromptEngine), ("fake", FakeCreativeEngine)])
def test_r006_build_services_selects_engine(engine_name: str, engine_type: type) -> None:
    settings = Settings(cost_table=REPO_ROOT / "config" / "cost_table.example.json",
                        creative_engine=engine_name, claude_model=TEST_MODEL)

    services = build_services(settings)

    assert isinstance(services.orchestrator.deps.engine, engine_type)


def sse_body(text: str, stop_reason: str) -> bytes:
    events = [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_test", "type": "message", "role": "assistant", "model": TEST_MODEL, "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 120, "output_tokens": 0}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "text_delta", "text": text}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta",
                           "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                           "usage": {"output_tokens": 45}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events).encode()


class MockAnthropic:
    """攔截 Anthropic SDK 的 HTTP 請求（不連網），回傳串流格式的回應。"""

    def __init__(self, text: str = '{"plans": []}', stop_reason: str = "end_turn") -> None:
        self.text, self.stop_reason = text, stop_reason
        self.requests: list[httpx2.Request] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return httpx2.Response(200, headers={"content-type": "text/event-stream"},
                               content=sse_body(self.text, self.stop_reason))

    def client(self) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.MockTransport(self.handler))

    def body(self) -> dict[str, Any]:
        (request,) = self.requests
        data: dict[str, Any] = json.loads(request.content)
        return data


SCHEMA = {"type": "object", "properties": {"plans": {"type": "array", "items": {"type": "string"}}},
          "required": ["plans"], "additionalProperties": False}


async def test_r006_anthropic_client_request_shape() -> None:
    mock = MockAnthropic(text='{"plans": ["a"]}')
    settings = Settings(claude_model=TEST_MODEL, claude_effort="high", anthropic_api_key=FAKE_KEY)
    client = AnthropicClaudeClient(settings, http_client=mock.client())

    reply = await client.complete(system="SYS", messages=[{"role": "user", "content": "U"}], schema=SCHEMA)

    assert reply == ClaudeReply(text='{"plans": ["a"]}', stop_reason="end_turn")
    body = mock.body()
    assert body["model"] == TEST_MODEL
    assert body["output_config"] == {"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}}
    assert body["system"] == "SYS"
    assert body["messages"] == [{"role": "user", "content": "U"}]
    assert body["stream"] is True
    assert body["fallbacks"] == "default"
    assert "thinking" not in body
    request = mock.requests[0]
    assert "server-side-fallback-2026-07-01" in request.headers["anthropic-beta"]
    assert request.headers["x-api-key"] == FAKE_KEY


async def test_r006_fallback_can_be_disabled() -> None:
    mock = MockAnthropic()
    settings = Settings(claude_model="another-model", claude_refusal_fallback=False,
                        anthropic_api_key=FAKE_KEY)

    await AnthropicClaudeClient(settings, http_client=mock.client()).complete(
        system="S", messages=[{"role": "user", "content": "U"}], schema=SCHEMA)

    body = mock.body()
    assert body["model"] == "another-model"
    assert body["output_config"]["effort"] == "medium"
    assert "fallbacks" not in body
    assert "server-side-fallback" not in mock.requests[0].headers.get("anthropic-beta", "")


async def test_r006_anthropic_client_reports_refusal() -> None:
    mock = MockAnthropic(text="", stop_reason="refusal")
    settings = Settings(claude_model=TEST_MODEL, anthropic_api_key=FAKE_KEY)

    reply = await AnthropicClaudeClient(settings, http_client=mock.client()).complete(
        system="S", messages=[{"role": "user", "content": "U"}], schema=SCHEMA)

    assert reply.stop_reason == "refusal"
