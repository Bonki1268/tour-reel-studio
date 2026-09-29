from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import REPO_ROOT, load_settings
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


def table() -> CostTable:
    return CostTable.from_rows(
        [
            {"kind": "keyframe", "model": "img-model-a", "credits": 5},
            {"kind": "video", "model": "vid-model-a", "credits": 30},
        ]
    )


def budget(cap: int, spent: int = 0) -> Budget:
    entries = [CostEntry("earlier-job", Decimal(spent), "table")] if spent else []
    return Budget(cap=Decimal(cap), entries=entries)


def test_r001_zero_shots_costs_nothing() -> None:
    estimate = estimate_video(table(), 0, "img-model-a", "vid-model-a")

    assert (estimate.total, estimate.reserve, estimate.cap) == (0, 0, 0)


def test_r001_reserve_shots_configurable() -> None:
    assert estimate_video(table(), 3, "img-model-a", "vid-model-a", reserve_shots=0).cap == 105
    assert estimate_video(table(), 3, "img-model-a", "vid-model-a", reserve_shots=2).cap == 175


def test_r001_reserve_shots_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    assert load_settings().retry_reserve_shots == 1

    monkeypatch.setenv("RETRY_RESERVE_SHOTS", "2")
    assert load_settings().retry_reserve_shots == 2

    monkeypatch.setenv("RETRY_RESERVE_SHOTS", "-1")
    with pytest.raises(ValidationError):
        load_settings()


def test_r002_exactly_at_cap_allowed() -> None:
    b = budget(140, spent=110)

    b.check("job-1", Decimal(30))

    assert b.reserved == {"job-1": Decimal(30)}


def test_r002_parallel_jobs_count_reservations() -> None:
    b = budget(140)
    for n in range(4):
        b.check(f"job-{n}", Decimal(35))

    with pytest.raises(BudgetExceeded):
        b.check("job-5", Decimal(1))
    assert sum(b.reserved.values()) == 140
    assert b.spent == 0


def test_r003_one_over_cap_rejected_without_side_effects() -> None:
    b = budget(140, spent=111)
    b.check("job-in-flight", Decimal(0))
    before = (list(b.entries), dict(b.reserved))

    with pytest.raises(BudgetExceeded) as exc:
        b.check("job-1", Decimal(30))

    assert str(exc.value).startswith("超出預算上限")
    assert exc.value.requires_reconfirmation is True
    assert (b.entries, b.reserved) == before


def test_r004_actual_cost_replaces_estimate() -> None:
    b = budget(140, spent=10)
    b.check("job-1", Decimal(30))

    entry = b.record("job-1", JobKind.VIDEO, "vid-model-a", Decimal(28), table())

    assert entry == CostEntry("job-1", Decimal(28), "provider")
    assert b.spent == 38
    assert b.reserved == {}


def test_r004_same_job_recorded_once() -> None:
    b = budget(140)
    b.check("job-1", Decimal(30))
    b.record("job-1", JobKind.VIDEO, "vid-model-a", Decimal(28), table())

    again = b.record("job-1", JobKind.VIDEO, "vid-model-a", Decimal(28), table())

    assert again is None
    assert len(b.entries) == 1
    assert b.spent == 28


VALID_FILE = '{"unit": "credits", "prices": [{"kind": "keyframe", "model": "m", "credits": "1.28"}]}'


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (None, "不存在"),
        ("not json", "JSON"),
        ('{"unit": "credits"}', "prices"),
        ('{"prices": [{"kind": "keyframe", "credits": 1}]}', "model"),
        ('{"prices": [{"kind": "audio", "model": "m", "credits": 1}]}', "audio"),
        ('{"prices": [{"kind": "video", "model": "m", "credits": -1}]}', "負數"),
        ('{"prices": [{"kind": "video", "model": "m", "credits": "abc"}]}', "credits"),
        (
            '{"prices": [{"kind": "video", "model": "m", "credits": 1},'
            ' {"kind": "video", "model": "m", "credits": 2}]}',
            "重複",
        ),
    ],
)
def test_r006_invalid_cost_table_files(tmp_path: Path, content: str | None, reason: str) -> None:
    path = tmp_path / "cost_table.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")

    with pytest.raises(CostTableError) as exc:
        CostTable.load(path)

    assert reason in str(exc.value)
    assert str(path) in str(exc.value)


def test_r006_load_cost_table_file(tmp_path: Path) -> None:
    path = tmp_path / "cost_table.json"
    path.write_text(VALID_FILE, encoding="utf-8")

    loaded = CostTable.load(path)

    assert loaded.price(JobKind.KEYFRAME, "m") == Decimal("1.28")
    with pytest.raises(CostTableError, match="unknown-model"):
        loaded.price(JobKind.VIDEO, "unknown-model")


def test_r006_example_cost_table_loads() -> None:
    example = CostTable.load(REPO_ROOT / "config" / "cost_table.example.json")

    assert example.price(JobKind.KEYFRAME, "xai/grok-imagine-image-2.0") == Decimal("1.28")
