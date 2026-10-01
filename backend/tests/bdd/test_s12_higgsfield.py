import asyncio
import json
import logging
import os
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest
from pydantic import SecretStr
from pytest_bdd import given, parsers, scenarios, then, when

from app.api.main import create_app
from app.config import Settings
from app.domain.cost import CostTable, JobKind
from app.providers.base import ProviderError, ProviderJob, ProviderRequest
from app.providers.higgsfield import HiggsfieldProvider
from app.providers.webhook import sign
from app.storage import keys
from tests.api_support import ApiEnv
from tests.generation_support import GenEnv
from tests.higgsfield_support import (
    API_KEY,
    BASE,
    IMAGE_MODEL,
    KEY_ID,
    KEY_SECRET,
    KEYFRAME_KEY,
    REQUEST_ID,
    RESULT_VIDEO_URL,
    VIDEO_MODEL,
    WEBHOOK_SECRET,
    HfMock,
    compose_request,
    hf_mock,
    hf_settings,
    i2v_request,
    provider,
    seeded_storage,
)

pytestmark = pytest.mark.S12

scenarios("api/s12_higgsfield.feature")


def run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.fixture
def ctx() -> dict[str, Any]:
    return {}


@pytest.fixture
def hf() -> Iterator[HfMock]:
    yield from hf_mock()


@given("以 HTTP mock 模擬 Higgsfield API")
def mocked(ctx: dict[str, Any], hf: HfMock) -> None:
    ctx["hf"] = hf
    ctx["storage"] = run(seeded_storage())
    ctx["provider"] = provider(ctx["storage"])


# S12-01


@when("以關鍵幀與提示詞送出圖生影片請求")
def submit_i2v(ctx: dict[str, Any]) -> None:
    ctx["job"] = run(ctx["provider"].image_to_video(i2v_request("pik-i2v")))
    ctx["model"] = VIDEO_MODEL


@then("請求使用設定檔的 HF_VIDEO_MODEL")
def uses_video_model(ctx: dict[str, Any]) -> None:
    hf: HfMock = ctx["hf"]
    calls = hf.submit_calls(VIDEO_MODEL)
    assert len(calls) == 1
    assert calls[0].url.host == "hf.test"
    assert calls[0].headers["Authorization"] == f"Key {API_KEY}"
    assert calls[0].headers["Idempotency-Key"] == "pik-i2v"
    assert ctx["job"].model == VIDEO_MODEL


@then("請求帶入關鍵幀網址與提示詞")
def i2v_body(ctx: dict[str, Any]) -> None:
    hf: HfMock = ctx["hf"]
    body = hf.submitted_body(VIDEO_MODEL)
    assert body["image_url"] == hf.public_url(1)
    assert hf.uploads == [b"keyframe-png"]
    assert body["prompt"] == "Guide waves"


@then("請求關閉音訊生成")
def no_audio(ctx: dict[str, Any]) -> None:
    assert ctx["hf"].submitted_body(VIDEO_MODEL)["generate_audio"] is False


@then("回傳包含 external_id 的 ProviderJob")
def provider_job(ctx: dict[str, Any]) -> None:
    job: ProviderJob = ctx["job"]
    assert isinstance(job, ProviderJob)
    assert job.external_id == REQUEST_ID
    assert job.provider == "higgsfield"


# S12-02


@when("以粗合成圖、遮罩與身份板送出合成請求")
def submit_compose(ctx: dict[str, Any]) -> None:
    ctx["job"] = run(ctx["provider"].compose(compose_request("pik-compose")))


@then("請求使用設定檔的 HF_IMAGE_MODEL")
def uses_image_model(ctx: dict[str, Any]) -> None:
    hf: HfMock = ctx["hf"]
    body = hf.submitted_body(IMAGE_MODEL)
    assert body["image_urls"] == [hf.public_url(1), hf.public_url(2)]
    assert hf.uploads == [b"rough-png", b"board-png"]
    assert body["aspect_ratio"] == "9:16"
    assert body["prompt"] == "Keep the background exactly unchanged."
    assert hf.submit_calls(VIDEO_MODEL) == []
    assert ctx["job"].model == IMAGE_MODEL


# S12-03


@given(parsers.parse('查詢狀態依序回傳 "{a}", "{b}", "{c}"'))
def status_sequence(ctx: dict[str, Any], a: str, b: str, c: str) -> None:
    hf: HfMock = ctx["hf"]
    hf.statuses[:] = [{"status": a}, {"status": b}, {"status": c, "video": {"url": RESULT_VIDEO_URL}}]


@when("輪詢該工作")
def poll(ctx: dict[str, Any]) -> None:
    job = ProviderJob("higgsfield", VIDEO_MODEL, REQUEST_ID)

    async def loop() -> list[Any]:
        results = []
        for _ in range(5):
            result = await ctx["provider"].fetch_result(job)
            results.append(result)
            if result.state != "running":
                break
        return results

    ctx["results"] = run(loop())


@then("取得結果網址")
def result_url(ctx: dict[str, Any]) -> None:
    states = [r.state for r in ctx["results"]]
    assert states == ["running", "running", "succeeded"]
    assert ctx["results"][-1].url == RESULT_VIDEO_URL


# S12-04


@given("一個已完成的工作")
def completed_job(ctx: dict[str, Any]) -> None:
    hf: HfMock = ctx["hf"]
    hf.statuses[:] = [{"status": "completed", "video": {"url": RESULT_VIDEO_URL}}]
    env = GenEnv()
    gctx = run(env.setup())
    run(env.storage.put(KEYFRAME_KEY, b"keyframe-png", "image/png"))
    settings = hf_settings()
    hp = HiggsfieldProvider(settings, env.storage)
    table = CostTable.from_rows(
        [
            {"kind": "keyframe", "model": IMAGE_MODEL, "credits": "1.28"},
            {"kind": "video", "model": VIDEO_MODEL, "credits": "4"},
        ]
    )
    env.ctx = replace(
        gctx, image_provider=hp, video_provider=hp, results=hp, settings=settings, cost_table=table
    )
    ctx["env"] = env


@when("取得結果")
def fetch(ctx: dict[str, Any]) -> None:
    env: GenEnv = ctx["env"]
    ctx["gen_job"] = run(
        env.run(JobKind.VIDEO, snapshot={"shot_no": 1, "keyframe_key": KEYFRAME_KEY, "prompt": "Guide waves"})
    )


@then("檔案下載至自有物件儲存")
def stored(ctx: dict[str, Any]) -> None:
    env: GenEnv = ctx["env"]
    assert ctx["gen_job"].status == "stored"
    assert env.video is not None and env.take is not None
    key = keys.clip(env.video.id, 1, env.take.attempt)
    assert run(env.storage.get(key)) == b"mp4-bytes"
    assert any(c.request.url == RESULT_VIDEO_URL for c in ctx["hf"].router.calls)


@then("生成工作只記錄自有儲存路徑")
def only_own_paths(ctx: dict[str, Any]) -> None:
    env: GenEnv = ctx["env"]
    assert env.video is not None and env.shot is not None and env.take is not None
    job = run(env.repos.jobs.get(ctx["gen_job"].id))
    takes = run(env.repos.shots.takes(env.shot.id))
    take = next(t for t in takes if t.id == env.take.id)
    assert take.clip_key == keys.clip(env.video.id, 1, env.take.attempt)
    dumped = json.dumps([vars(job), vars(take)], default=str)
    assert "hf.test" not in dumped


# S12-05


class _NoTouch:
    """任何存取都記錄下來：webhook 驗證失敗時不可讀寫生成工作。"""

    def __init__(self) -> None:
        self.touched: list[str] = []

    def __getattr__(self, name: str) -> Any:
        self.touched.append(name)
        raise AssertionError(f"webhook 不可存取 jobs.{name}")


def _webhook_client(ctx: dict[str, Any]) -> tuple[ApiEnv, _NoTouch]:
    env = ApiEnv()
    services = env.services
    services.settings = services.settings.model_copy(
        update={"higgsfield_webhook_secret": SecretStr(WEBHOOK_SECRET), "public_base_url": "https://trs.test"}
    )
    guard = _NoTouch()
    services.repos.jobs = guard
    env._app = create_app(services.settings, services)
    return env, guard


@when("以錯誤的簽章呼叫 POST /webhooks/higgsfield")
def wrong_signature(ctx: dict[str, Any]) -> None:
    env, guard = _webhook_client(ctx)
    good = sign(WEBHOOK_SECRET, "pik-1")
    bad = ("0" if good[0] != "0" else "1") + good[1:]
    payload = {
        "request_id": REQUEST_ID,
        "status": "completed",
        "error": None,
        "payload": {"video": {"url": "https://evil.test/x.mp4"}},
    }
    ctx["response"] = run(
        env.request("POST", "/webhooks/higgsfield", params={"ref": "pik-1", "sig": bad}, json=payload)
    )
    ctx["missing"] = run(env.request("POST", "/webhooks/higgsfield", params={"ref": "pik-1"}, json=payload))
    ctx["guard"] = guard


@then(parsers.parse("回應狀態碼為 {code:d}"))
def status_code(ctx: dict[str, Any], code: int) -> None:
    assert ctx["response"].status_code == code
    assert ctx["missing"].status_code == code
    assert ctx["response"].json()["code"] == "invalid_signature"


@then("不更新任何生成工作")
def no_job_touched(ctx: dict[str, Any]) -> None:
    assert ctx["guard"].touched == []


# S12-06


@given(parsers.parse("Higgsfield 回應 HTTP {status:d}"))
def hf_error(ctx: dict[str, Any], status: int) -> None:
    hf: HfMock = ctx["hf"]
    hf.router.post(f"{BASE}/{VIDEO_MODEL}").respond(status, json={"detail": f"error {status}"})


@when("送出圖生影片請求")
def submit_failing(ctx: dict[str, Any]) -> None:
    with pytest.raises(ProviderError) as exc:
        run(ctx["provider"].image_to_video(i2v_request()))
    ctx["error"] = exc.value


@then(parsers.parse('錯誤被歸類為 "{kind}"'))
def classified(ctx: dict[str, Any], kind: str) -> None:
    expected = {"retryable": True, "non_retryable": False}[kind]
    assert ctx["error"].retryable is expected


# S12-07


@when("送出圖生影片請求並記錄日誌")
def submit_with_logs(ctx: dict[str, Any], caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    for name in ("httpx", "httpcore", "app"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    hf: HfMock = ctx["hf"]
    hf.statuses[:] = [{"status": "in_progress"}]
    p: HiggsfieldProvider = ctx["provider"]
    job = run(p.image_to_video(i2v_request()))
    run(p.fetch_result(job))
    logging.getLogger("httpx").debug("headers: Authorization: Key %s", API_KEY)  # 模擬第三方記錄標頭
    hf.router.post(f"{BASE}/{IMAGE_MODEL}").respond(401, json={"detail": f"invalid key {API_KEY}"})
    with pytest.raises(ProviderError) as exc:
        run(p.compose(compose_request()))
    ctx["log_text"] = caplog.text + "\n".join(r.getMessage() for r in caplog.records) + str(exc.value)


@then("日誌中找不到 API 金鑰")
def no_key_in_logs(ctx: dict[str, Any]) -> None:
    text = ctx["log_text"]
    assert "hf.test" in text  # 確實有記錄到請求
    assert API_KEY not in text
    assert KEY_SECRET not in text
    assert KEY_ID not in text


# S12-08（external：不列入閘門，只在使用者同意並設定金鑰時執行）


@given("已設定真實的 HIGGSFIELD_API_KEY")
def live_key(ctx: dict[str, Any], hf: HfMock) -> None:
    hf.router.stop()
    key, model = os.environ.get("TRS_LIVE_HIGGSFIELD_API_KEY"), os.environ.get("TRS_LIVE_HF_VIDEO_MODEL")
    keyframe = os.environ.get("TRS_LIVE_KEYFRAME_PNG")
    if not key or not model or not keyframe:
        pytest.skip("未設定 TRS_LIVE_HIGGSFIELD_API_KEY／TRS_LIVE_HF_VIDEO_MODEL／TRS_LIVE_KEYFRAME_PNG")
    settings = Settings(higgsfield_api_key=SecretStr(key), hf_video_model=model, webhook_enabled=False)
    run(ctx["storage"].put(KEYFRAME_KEY, open(keyframe, "rb").read(), "image/png"))
    ctx["live"] = HiggsfieldProvider(settings, ctx["storage"])
    ctx["live_model"] = model


@when("以測試關鍵幀送出一次圖生影片請求")
def live_submit(ctx: dict[str, Any]) -> None:
    req = ProviderRequest(
        ctx["live_model"],
        {"keyframe_key": KEYFRAME_KEY, "prompt": "Slow subtle push-in", "duration_s": 4},
        "trs-live-smoke",
    )
    ctx["live_job"] = run(ctx["live"].image_to_video(req))


@then("在 10 分鐘內取得可播放的影片")
def live_result(ctx: dict[str, Any]) -> None:
    async def wait() -> tuple[bytes, str]:
        for _ in range(120):
            result = await ctx["live"].fetch_result(ctx["live_job"])
            if result.state == "succeeded":
                return tuple(await ctx["live"].download(result))  # type: ignore[return-value]
            assert result.state == "running", result.error
            await asyncio.sleep(5)
        raise AssertionError("10 分鐘內未完成")

    content, content_type = run(wait())
    assert content_type.startswith("video/") and len(content) > 10_000
