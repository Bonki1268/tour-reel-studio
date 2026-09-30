import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, scenarios, then, when

from app.domain.approval import ApprovalKind
from tests.api_support import ApiEnv, as_decimal
from tests.live_server import LiveServer, SseReader

pytestmark = pytest.mark.S08


# 自動產生的名稱 test_s0804_狀態不符時回應_409 經閘門正規化（去掉中文）後，編號緊接數字 409 而無法比對；
# 改以明確名稱綁定
@scenario("api/s08_api.feature", "S08-04 狀態不符時回應 409")
def test_s0804_conflicting_state() -> None:
    pass


scenarios("api/s08_api.feature")


@pytest.fixture
def ctx() -> Iterator[dict[str, Any]]:
    c: dict[str, Any] = {"cleanup": []}
    yield c
    for fn in reversed(c["cleanup"]):
        fn()


def run(coro: Any) -> Any:
    return asyncio.run(coro)


# Background


@given("一個含品牌檔案、1 個已鎖定角色與 3 張實景照的專案")
def project(ctx: dict[str, Any]) -> None:
    env = ApiEnv(keepalive_s=0.2)
    ctx["env"] = env
    ctx["project_id"] = run(env.setup_project())


@given(parsers.parse('影片狀態為 "{status}"'))
def video_in_status(ctx: dict[str, Any], status: str) -> None:
    env: ApiEnv = ctx["env"]
    ctx["video_id"] = run(env.video_in(status))
    assert run(env.status(ctx["video_id"])) == status


# S08-01


@when(parsers.parse('以主題 "{topic}" 呼叫 POST /projects/{{id}}/videos'))
def post_video(ctx: dict[str, Any], topic: str) -> None:
    env: ApiEnv = ctx["env"]
    ctx["response"] = run(env.request("POST", f"/projects/{ctx['project_id']}/videos", json={"topic": topic}))


@then(parsers.parse("回應狀態碼為 {code:d}"))
def status_code_is(ctx: dict[str, Any], code: int) -> None:
    assert ctx["response"].status_code == code, ctx["response"].text


@then(parsers.parse('影片狀態為 "{status}"'))
def response_status_is(ctx: dict[str, Any], status: str) -> None:
    env: ApiEnv = ctx["env"]
    body = ctx["response"].json()
    assert body["status"] == status
    assert env.queued("plan_video") == [{"video_id": body["id"]}]


# S08-02、S08-03


@when("以相同 Idempotency-Key 呼叫 POST /videos/{id}/approve-plan 兩次")
def approve_twice(ctx: dict[str, Any]) -> None:
    env: ApiEnv = ctx["env"]
    ctx["responses"] = [run(env.approve_plan(ctx["video_id"], key="same-key")) for _ in range(2)]


@then(parsers.parse("兩次都回應 {code:d}"))
def both_responses(ctx: dict[str, Any], code: int) -> None:
    first, second = ctx["responses"]
    assert first.status_code == second.status_code == code, (first.text, second.text)
    assert first.json() == second.json()


@then("只建立一組生成工作")
def single_generation(ctx: dict[str, Any]) -> None:
    env: ApiEnv = ctx["env"]
    vid = ctx["video_id"]
    approvals = run(env.repos.approvals.list(vid))
    assert [a.kind for a in approvals].count(ApprovalKind.PLAN) == 1
    assert len(run(env.repos.shots.list_shots(vid))) == 3
    assert env.queued("generate_video") == [{"video_id": vid}]


@when("呼叫 POST /videos/{id}/approve-plan 但沒有提供 cost_cap")
def approve_without_cap(ctx: dict[str, Any]) -> None:
    env: ApiEnv = ctx["env"]
    body = run(env.first_plan_body(ctx["video_id"]))
    del body["cost_cap"]
    ctx["response"] = run(env.request(
        "POST", f"/videos/{ctx['video_id']}/approve-plan", json=body, headers={"Idempotency-Key": "k-1"}
    ))
    assert run(env.status(ctx["video_id"])) == "plan_ready"


# S08-04


@when("呼叫 POST /videos/{id}/plans/regenerate")
def regenerate_plans(ctx: dict[str, Any]) -> None:
    env: ApiEnv = ctx["env"]
    ctx["response"] = run(env.request("POST", f"/videos/{ctx['video_id']}/plans/regenerate"))
    assert ctx["response"].json()["code"] == "invalid_state"
    assert run(env.status(ctx["video_id"])) == "generating"
    assert env.queued("regenerate_plans") == []


# S08-05


@given("已訂閱 GET /videos/{id}/events")
def subscribed(ctx: dict[str, Any]) -> None:
    env: ApiEnv = ctx["env"]
    ctx["video_id"] = run(env.create_video())
    server = LiveServer(env.app)
    server.start()
    ctx["cleanup"].append(server.stop)
    reader = SseReader(f"{server.base_url}/videos/{ctx['video_id']}/events")
    reader.start()
    ctx["cleanup"].append(reader.stop)
    status = reader.wait_for("status")
    assert status["status"] == "planning" and status["video_id"] == ctx["video_id"]
    ctx["reader"] = reader


@when(parsers.parse('影片狀態變為 "{status}"'))
def worker_runs(ctx: dict[str, Any], status: str) -> None:
    env: ApiEnv = ctx["env"]
    run(env.run_jobs())
    assert run(env.status(ctx["video_id"])) == status


@then(parsers.parse('收到事件 "{event_type}"'))
def event_received(ctx: dict[str, Any], event_type: str) -> None:
    data = ctx["reader"].wait_for(event_type)
    assert data["type"] == event_type
    assert data["video_id"] == ctx["video_id"]
    assert "at" in data


# S08-06


@when("呼叫 GET /videos/{id}/download")
def download(ctx: dict[str, Any]) -> None:
    ctx["response"] = run(ctx["env"].request("GET", f"/videos/{ctx['video_id']}/download"))


@then(parsers.parse("回應包含有效期不超過 {minutes:d} 分鐘的下載網址"))
def short_lived_url(ctx: dict[str, Any], minutes: int) -> None:
    env: ApiEnv = ctx["env"]
    r = ctx["response"]
    assert r.status_code == 200, r.text
    body = r.json()
    expires_at = datetime.fromisoformat(body["expires_at"])
    now = datetime.now(UTC)
    assert now < expires_at <= now + timedelta(minutes=minutes)
    renders = run(env.repos.renders.list(ctx["video_id"]))
    assert renders[-1].mp4_key in body["url"]


# S08-07


@when("呼叫 GET /videos/{id}")
def get_video(ctx: dict[str, Any]) -> None:
    ctx["response"] = run(ctx["env"].request("GET", f"/videos/{ctx['video_id']}"))


@then("回應包含 status、plans、shots、cost_cap 與 spent")
def video_fields(ctx: dict[str, Any]) -> None:
    env: ApiEnv = ctx["env"]
    r = ctx["response"]
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "review"
    assert 2 <= len(body["plans"]) <= 3
    assert all({"total", "reserve", "cap"} <= set(p["estimate"]) for p in body["plans"])
    assert [s["shot_no"] for s in body["shots"]] == [1, 2, 3]
    assert all(s["take"]["keyframe_key"] and s["take"]["clip_key"] for s in body["shots"])
    costs = run(env.repos.costs.list(ctx["video_id"]))
    assert as_decimal(body["spent"]) == sum((c.credits for c in costs), as_decimal(0))
    assert as_decimal(body["cost_cap"]) > 0
    assert body["preview_url"]
