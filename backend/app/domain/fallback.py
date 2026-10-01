"""保底成品（spec 0018 R-006）：生成超過展示門檻時提供事先準備的成品。"""

from datetime import datetime

from app.domain.video import Video


def fallback_due(video: Video, now: datetime, after_s: float, *, has_render: bool) -> bool:
    raise NotImplementedError
