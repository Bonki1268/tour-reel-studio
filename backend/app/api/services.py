"""API 與 Worker 共用的服務組合（spec 0008）。測試注入記憶體版；正式環境由設定建立。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.config import Settings
from app.domain.ports import Repositories, Storage
from app.domain.video import utc_now
from app.jobs.events import EventBus
from app.jobs.orchestrator import QuickModeOrchestrator
from app.jobs.queue import JobQueue


@dataclass
class AppServices:
    settings: Settings
    repos: Repositories
    storage: Storage
    orchestrator: QuickModeOrchestrator
    queue: JobQueue
    events: EventBus
    clock: Callable[[], datetime] = utc_now


def build_services(settings: Settings) -> AppServices:
    """依設定建立正式環境的服務（資料庫 repository、arq 佇列、Redis 事件）。

    S08 時創作引擎、供應商與合成器仍為假實作（S10、S12、S13 替換）；物件儲存為記憶體版（S09 替換）。
    """
    raise NotImplementedError
