"""保底成品（spec 0018 R-006）：生成超過展示門檻時提供事先準備的成品。"""

from datetime import datetime, timedelta

from app.domain.video import Video, VideoStatus

FALLBACK_STATUSES = frozenset({VideoStatus.GENERATING, VideoStatus.RENDERING, VideoStatus.NEEDS_ATTENTION})


def fallback_due(video: Video, now: datetime, after_s: float, *, has_render: bool) -> bool:
    """尚無成品、狀態仍在生成流程中，且距最後一次進入 generating 已達門檻。"""
    if has_render or video.status not in FALLBACK_STATUSES:
        return False
    started = [c.at for c in video.history if c.to_status == VideoStatus.GENERATING]
    return bool(started) and now - started[-1] >= timedelta(seconds=after_s)
