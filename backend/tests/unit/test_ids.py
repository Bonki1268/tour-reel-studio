import pytest

from app.domain.ids import idempotency_key, new_id

pytestmark = pytest.mark.S05


def test_r004_idempotency_key_format() -> None:
    assert idempotency_key(video_id="v1", shot_no=1, kind="keyframe", input_hash="abc", attempt=1) == (
        "v1:1:keyframe:abc:1"
    )
    assert idempotency_key("9f1c", 3, "video", "deadbeef", 2) == "9f1c:3:video:deadbeef:2"


@pytest.mark.parametrize(
    "parts",
    [
        {"video_id": ""},
        {"kind": ""},
        {"input_hash": ""},
        {"video_id": "v:1"},
        {"kind": "key:frame"},
        {"input_hash": "a:b"},
        {"shot_no": 0},
        {"attempt": 0},
        {"attempt": -1},
    ],
)
def test_r004_idempotency_key_rejects_invalid_parts(parts: dict[str, object]) -> None:
    args: dict[str, object] = {
        "video_id": "v1", "shot_no": 1, "kind": "keyframe", "input_hash": "abc", "attempt": 1,
    }
    args.update(parts)
    with pytest.raises(ValueError):
        idempotency_key(**args)  # type: ignore[arg-type]


def test_r004_new_id_is_unique_uuid_string() -> None:
    ids = {new_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(len(i) == 36 for i in ids)
