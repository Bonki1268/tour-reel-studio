"""識別碼：主鍵與生成工作冪等鍵（spec 0005 R-004）。"""


def new_id() -> str:
    raise NotImplementedError


def idempotency_key(video_id: str, shot_no: int, kind: str, input_hash: str, attempt: int) -> str:
    raise NotImplementedError
