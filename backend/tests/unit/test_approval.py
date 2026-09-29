from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.domain.approval import (
    Approval,
    ApprovalError,
    ApprovalInvalidated,
    ApprovalKind,
    auto_approve,
    canonical_hash,
    check_before_submit,
    ensure_still_approved,
    plan_approval_input,
)
from app.domain.video import Video, VideoStatus

pytestmark = pytest.mark.S03

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
PLAN = {"id": "P1", "shots": [{"shot_no": 1, "role": "hook"}, {"shot_no": 2, "role": "feature"}]}


def placement(shot_no: int, x: float = 0.5) -> dict[str, object]:
    return {"shot_no": shot_no, "x": x, "y": 0.8, "scale": 0.6, "flip": False}


def make_approval(**overrides: object) -> Approval:
    fields: dict[str, object] = {
        "kind": ApprovalKind.PLAN,
        "input_hash": "0" * 64,
        "cost_cap": Decimal("140"),
        "auto_approved": False,
        "approved_by": "bonki",
        "approved_at": NOW,
    }
    fields.update(overrides)
    return Approval(**fields)  # type: ignore[arg-type]


def test_r002_hash_ignores_key_order() -> None:
    a = {"plan": {"id": "P1", "meta": {"a": 1, "b": [1, 2]}}, "x": 0.5}
    b = {"x": 0.5, "plan": {"meta": {"b": [1, 2], "a": 1}, "id": "P1"}}

    assert canonical_hash(a) == canonical_hash(b)
    assert len(canonical_hash(a)) == 64


def test_r002_hash_depends_on_list_order() -> None:
    assert canonical_hash({"shots": [1, 2, 3]}) != canonical_hash({"shots": [2, 1, 3]})


def test_r002_float_rounded_to_4_places() -> None:
    assert canonical_hash({"x": 0.12344}) == canonical_hash({"x": 0.12341})
    assert canonical_hash({"x": 0.1 + 0.2}) == canonical_hash({"x": 0.3})
    assert canonical_hash({"x": 0.1234}) != canonical_hash({"x": 0.1235})


def test_r002_int_and_integral_float_equal() -> None:
    assert canonical_hash({"x": 1}) == canonical_hash({"x": 1.0})
    assert canonical_hash({"x": 0}) == canonical_hash({"x": -0.0})
    assert canonical_hash({"x": Decimal("1.280")}) == canonical_hash({"x": Decimal("1.28")})


def test_r002_rejects_nan_and_unsupported_types() -> None:
    with pytest.raises(ValueError):
        canonical_hash({"x": float("nan")})
    with pytest.raises(ValueError):
        canonical_hash({"x": float("inf")})
    with pytest.raises(TypeError):
        canonical_hash({"at": NOW})
    with pytest.raises(TypeError):
        canonical_hash({1: "non-string key"})


def test_r001_placement_order_does_not_matter() -> None:
    forward = plan_approval_input(PLAN, [placement(1), placement(2)])
    backward = plan_approval_input(PLAN, [placement(2), placement(1)])

    assert canonical_hash(forward) == canonical_hash(backward)


def test_r004_rejected_submit_returns_video_to_plan_ready() -> None:
    approved_input = plan_approval_input(PLAN, [placement(1), placement(2)])
    changed_input = plan_approval_input(PLAN, [placement(1), placement(2, x=0.1)])
    approval = make_approval(input_hash=canonical_hash(approved_input))

    ensure_still_approved(approval, approved_input)
    with pytest.raises(ApprovalInvalidated):
        ensure_still_approved(approval, changed_input)

    video = Video(status=VideoStatus.GENERATING)
    check_before_submit(video, approval, approved_input)
    assert video.status_trail == [VideoStatus.GENERATING]

    with pytest.raises(ApprovalInvalidated):
        check_before_submit(video, approval, changed_input)
    assert video.status_trail == [VideoStatus.GENERATING, VideoStatus.PLAN_READY]


def test_r005_plan_and_final_cannot_be_auto_approved() -> None:
    for kind in (ApprovalKind.PLAN, ApprovalKind.FINAL):
        with pytest.raises(ApprovalError):
            auto_approve(kind, {"any": "content"})
        with pytest.raises(ApprovalError):
            make_approval(kind=kind, auto_approved=True, approved_by=None)

    approval = auto_approve(ApprovalKind.KEYFRAMES, {"shots": [1, 2, 3]}, clock=lambda: NOW)
    assert approval.auto_approved is True
    assert approval.approved_by is None
    assert approval.approved_at == NOW


def test_r006_cost_cap_must_be_positive() -> None:
    for cap in (Decimal("0"), Decimal("-1")):
        with pytest.raises(ApprovalError):
            make_approval(cost_cap=cap)
    with pytest.raises(ApprovalError):
        make_approval(cost_cap=None)

    assert make_approval(cost_cap=Decimal("0.01")).cost_cap == Decimal("0.01")
    assert make_approval(kind=ApprovalKind.SCRIPT, cost_cap=None).cost_cap is None


def test_r006_unknown_kind_and_missing_approver_rejected() -> None:
    with pytest.raises(ApprovalError):
        make_approval(kind="storyboard")
    for approver in (None, "", "  "):
        with pytest.raises(ApprovalError):
            make_approval(approved_by=approver)
