"""Worker 工作函式與 arq 設定（spec 0008）。

啟動：`arq app.jobs.worker.WorkerSettings`（於 backend/）。記憶體佇列與 arq 共用 run_job。
"""

from typing import Any

from app.api.services import AppServices

JOB_NAMES = ("plan_video", "generate_video", "regenerate_plans", "regenerate_shot")


async def run_job(services: AppServices, name: str, **kwargs: Any) -> None:
    """依工作名稱執行 S07 編排。"""
    raise NotImplementedError


def arq_functions() -> list[Any]:
    """arq 工作函式：從 ctx["services"] 取得服務後呼叫 run_job。"""
    raise NotImplementedError
