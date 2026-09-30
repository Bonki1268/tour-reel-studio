"""API 與 Worker 共用的服務組合（spec 0008）。測試注入記憶體版；正式環境由設定建立。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.config import Settings
from app.creative.fake import FakeCreativeEngine
from app.domain.cost import CostTable
from app.domain.ports import Repositories, Storage
from app.domain.video import utc_now
from app.jobs.events import EventBus, RedisEventBus
from app.jobs.orchestrator import OrchestratorDeps, QuickModeOrchestrator
from app.jobs.queue import ArqJobQueue, JobQueue
from app.providers.fake import FakeProvider
from app.render.fake import FakeRenderer
from app.storage.db import create_engine
from app.storage.objects import S3Storage
from app.storage.sql_repos import sql_repositories


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

    創作引擎、供應商與合成器仍為假實作（S10、S12、S13 替換）；物件儲存為 S3 相容儲存（S09）。
    """
    repos = sql_repositories(create_engine(settings))
    storage = S3Storage(settings)
    events = RedisEventBus(settings.redis_url)
    provider = FakeProvider()
    orchestrator = QuickModeOrchestrator(OrchestratorDeps(
        repos=repos, storage=storage, engine=FakeCreativeEngine(), renderer=FakeRenderer(),
        image_provider=provider, video_provider=provider, results=provider, events=events,
        cost_table=CostTable.load(settings.cost_table), settings=settings,
    ))
    return AppServices(settings=settings, repos=repos, storage=storage, orchestrator=orchestrator,
                       queue=ArqJobQueue(settings.redis_url), events=events)
