"""Demo 可靠性（spec 0018）：webhook 觸發的結果處理與 Worker 啟動時的恢復掃描。"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from app.config import Settings
from app.domain.ports import Repositories
from app.jobs.orchestrator import OrchestratorDeps
from app.jobs.queue import JobQueue


@dataclass
class RecoveryReport:
    resumed: list[str] = field(default_factory=list)  # 接續輪詢的工作
    failed: list[str] = field(default_factory=list)  # 逾時或轉存中斷，標記為失敗的工作
    videos: list[str] = field(default_factory=list)  # 排入 generate_video 的影片


async def process_webhook(deps: OrchestratorDeps, job_id: str) -> str:
    raise NotImplementedError


async def recover(
    repos: Repositories, queue: JobQueue, settings: Settings, clock: Callable[[], datetime]
) -> RecoveryReport:
    raise NotImplementedError
