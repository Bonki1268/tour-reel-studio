"""識別碼：主鍵與生成工作冪等鍵（spec 0005 R-004）。"""

import uuid


def new_id() -> str:
    return str(uuid.uuid4())


def idempotency_key(video_id: str, shot_no: int, kind: str, input_hash: str, attempt: int) -> str:
    """`{video_id}:{shot_no}:{kind}:{input_hash}:{attempt}`；組成部分不可為空或含冒號。"""
    for name, part in (("video_id", video_id), ("kind", kind), ("input_hash", input_hash)):
        if not part or ":" in part:
            raise ValueError(f"冪等鍵的 {name} 不可為空或含冒號：{part!r}")
    if shot_no < 1 or attempt < 1:
        raise ValueError(f"冪等鍵的 shot_no 與 attempt 必須 ≥ 1：{shot_no}、{attempt}")
    return f"{video_id}:{shot_no}:{kind}:{input_hash}:{attempt}"
