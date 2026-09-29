from decimal import Decimal
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, scenarios, then, when

from app.domain.cost import (
    Budget,
    BudgetExceeded,
    CostEntry,
    CostTable,
    CostTableError,
    JobKind,
    estimate_video,
)

pytestmark = pytest.mark.S04


# 自動產生的名稱為 test_s0401_估算_3_鏡…，正規化後編號緊接數字 3，閘門無法比對；改以明確名稱綁定
@scenario("api/s04_cost.feature", "S04-01 估算 3 鏡影片的成本與上限")
def test_s0401_estimate_cost_and_cap() -> None:
    pass


scenarios("api/s04_cost.feature")

IMAGE_MODEL = "img-model-a"
VIDEO_MODEL = "vid-model-a"


@pytest.fixture
def ctx() -> dict[str, Any]:
    return {"error": None}


# Background


@given("單價表為")
def cost_table_is(ctx: dict[str, Any], datatable: list[list[str]]) -> None:
    header, *rows = datatable
    ctx["table"] = CostTable.from_rows([dict(zip(header, row, strict=True)) for row in rows])


@given(parsers.parse("成本上限預留 {shots:d} 鏡的完整重生費用"))
def reserve_shots(ctx: dict[str, Any], shots: int) -> None:
    ctx["reserve_shots"] = shots


# S04-01


@when(parsers.parse("估算一支 {shots:d} 鏡影片的成本"))
def estimate(ctx: dict[str, Any], shots: int) -> None:
    ctx["estimate"] = estimate_video(ctx["table"], shots, IMAGE_MODEL, VIDEO_MODEL, ctx["reserve_shots"])


@then(parsers.parse("預估成本為 {credits:d} 點"))
def estimated_total(ctx: dict[str, Any], credits: int) -> None:
    assert ctx["estimate"].total == Decimal(credits)


@then(parsers.parse("成本上限為 {credits:d} 點"))
def estimated_cap(ctx: dict[str, Any], credits: int) -> None:
    assert ctx["estimate"].cap == Decimal(credits)


# S04-02、S04-03


@given(parsers.parse("成本上限為 {cap:d} 點，已花費 {spent:d} 點"))
def budget_with_spent(ctx: dict[str, Any], cap: int, spent: int) -> None:
    ctx["budget"] = Budget(cap=Decimal(cap), entries=[CostEntry("earlier-job", Decimal(spent), "table")])


@when(parsers.parse("準備送出一個預估 {credits:d} 點的影片工作"))
def check_video_job(ctx: dict[str, Any], credits: int) -> None:
    budget: Budget = ctx["budget"]
    ctx["before"] = (budget.spent, dict(budget.reserved))
    try:
        budget.check("video-job", Decimal(credits))
    except BudgetExceeded as e:
        ctx["error"] = e


@then("允許送出")
def allowed(ctx: dict[str, Any]) -> None:
    assert ctx["error"] is None
    assert "video-job" in ctx["budget"].reserved


@then(parsers.parse("拒絕送出並回報「{message}」"))
def rejected_with(ctx: dict[str, Any], message: str) -> None:
    assert isinstance(ctx["error"], BudgetExceeded)
    assert message in str(ctx["error"])
    budget: Budget = ctx["budget"]
    assert (budget.spent, budget.reserved) == ctx["before"]


@then("影片需要使用者重新確認成本")
def needs_reconfirmation(ctx: dict[str, Any]) -> None:
    assert ctx["error"].requires_reconfirmation is True


# S04-04、S04-05


@given(parsers.parse("一個預估 {credits:d} 點的影片工作"))
def job_with_estimate(ctx: dict[str, Any], credits: int) -> None:
    ctx["budget"] = Budget(cap=Decimal(140))
    ctx["budget"].check("video-job", Decimal(credits))
    ctx["model"] = VIDEO_MODEL
    ctx["spent_before"] = ctx["budget"].spent


@given(parsers.parse('一個使用 "{model}" 的影片工作'))
def job_with_model(ctx: dict[str, Any], model: str) -> None:
    ctx["budget"] = Budget(cap=Decimal(140))
    ctx["budget"].check("video-job", ctx["table"].price(JobKind.VIDEO, model))
    ctx["model"] = model


@when(parsers.parse("供應商回報實際成本 {credits:d} 點"))
def provider_reports(ctx: dict[str, Any], credits: int) -> None:
    ctx["entry"] = ctx["budget"].record(
        "video-job", JobKind.VIDEO, ctx["model"], Decimal(credits), ctx["table"]
    )


@when("工作完成但供應商沒有回報成本")
def provider_silent(ctx: dict[str, Any]) -> None:
    ctx["entry"] = ctx["budget"].record("video-job", JobKind.VIDEO, ctx["model"], None, ctx["table"])


@then(parsers.parse("成本帳新增一筆 {credits:d} 點"))
def ledger_entry(ctx: dict[str, Any], credits: int) -> None:
    assert ctx["budget"].entries == [ctx["entry"]]
    assert ctx["entry"].credits == Decimal(credits)


@then(parsers.parse("已花費金額增加 {credits:d} 點"))
def spent_increased(ctx: dict[str, Any], credits: int) -> None:
    assert ctx["budget"].spent - ctx["spent_before"] == Decimal(credits)
    assert ctx["entry"].source == "provider"


# S04-06


@when(parsers.parse('估算使用 "{model}" 的工作成本'))
def estimate_unknown(ctx: dict[str, Any], model: str) -> None:
    try:
        ctx["table"].price(JobKind.VIDEO, model)
    except CostTableError as e:
        ctx["error"] = e


@then(parsers.parse('應拋出單價表錯誤並指出缺少 "{model}"'))
def cost_table_error(ctx: dict[str, Any], model: str) -> None:
    assert isinstance(ctx["error"], CostTableError)
    assert model in str(ctx["error"])
