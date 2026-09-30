"""Worker 工作函式與 arq 設定（spec 0008）。

啟動：`arq app.jobs.worker.WorkerSettings`（於 backend/）。記憶體佇列與 arq 共用 run_job。
"""

import logging
from typing import Any

from arq.connections import RedisSettings
from arq.typing import WorkerCoroutine
from arq.worker import Function, func

from app.api.errors import error_response
from app.api.services import AppServices, build_services
from app.config import load_settings
from app.domain.approval import ApprovalInvalidated
from app.domain.cost import BudgetExceeded
from app.domain.video import InvalidTransition
from app.jobs.events import ProgressEvent
from app.jobs.orchestrator import PlanningFailed

log = logging.getLogger(__name__)

JOB_NAMES = ("plan_video", "generate_video", "regenerate_plans", "regenerate_shot")

# 業務上可預期的失敗：影片狀態已由編排處理，發布 job_failed 事件後不再拋出
_EXPECTED = (ApprovalInvalidated, BudgetExceeded, PlanningFailed, InvalidTransition)


async def run_job(services: AppServices, name: str, **kwargs: Any) -> None:
    """依工作名稱執行 S07 編排。"""
    orch = services.orchestrator
    video_id: str = kwargs["video_id"]
    try:
        if name == "plan_video":
            await orch.propose_plans(video_id)
        elif name == "generate_video":
            await orch.generate(video_id)
        elif name == "regenerate_plans":
            await orch.regenerate_plans(video_id)
        elif name == "regenerate_shot":
            await orch.regenerate_shot(video_id, int(kwargs["shot_no"]))
        else:
            raise ValueError(f"未知的工作：{name}")
    except _EXPECTED as e:
        if not isinstance(e, PlanningFailed):  # 企劃失敗已發布 planning_failed
            code = error_response(e)[1]["code"]
            await services.events.publish(
                ProgressEvent("job_failed", video_id, services.clock(), data={"job": name, "code": code})
            )
        log.info("工作 %s（影片 %s）結束：%s", name, video_id, type(e).__name__)


def _arq_job(name: str) -> WorkerCoroutine:
    async def job(ctx: dict[str, Any], **kwargs: Any) -> None:
        await run_job(ctx["services"], name, **kwargs)

    job.__name__ = name
    return job


def arq_functions() -> list[Function]:
    """arq 工作函式：從 ctx["services"] 取得服務後呼叫 run_job。"""
    return [func(_arq_job(n), name=n) for n in JOB_NAMES]


async def _startup(ctx: dict[str, Any]) -> None:
    ctx["services"] = build_services(load_settings())


class WorkerSettings:
    functions = arq_functions()
    on_startup = _startup
    redis_settings = RedisSettings.from_dsn(load_settings().redis_url)
