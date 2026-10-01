"""S18 測試共用：可暫停的儲存與供應商（製造並行）、讓出事件迴圈的假時鐘。"""

import asyncio
from collections import Counter

from app.domain.ports import GenerationJob, Repositories
from app.providers.base import ProviderJob, ProviderResult
from app.providers.fake import FakeProvider
from app.storage.objects import MemoryStorage
from tests.generation_support import FakeClock


class GatedStorage(MemoryStorage):
    """記錄每個路徑的寫入次數；hold(key) 後，寫入該路徑會停住直到 release()。"""

    def __init__(self) -> None:
        super().__init__()
        self.puts: Counter[str] = Counter()
        self._held: str | None = None
        self.waiting = asyncio.Event()
        self._release = asyncio.Event()

    def hold(self, key: str) -> None:
        self._held = key

    def hold_suffix(self, suffix: str) -> None:
        self._held = "*" + suffix

    def release(self) -> None:
        self._release.set()

    def _matches(self, key: str) -> bool:
        if self._held is None:
            return False
        return key.endswith(self._held[1:]) if self._held.startswith("*") else key == self._held

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.puts[key] += 1
        if self._matches(key):
            self._held = None  # 只攔第一次
            self.waiting.set()
            await self._release.wait()
        await super().put(key, data, content_type)


class GatedProvider(FakeProvider):
    """查詢結果前先等待 gate；crash 為真時查詢直接拋出 WorkerCrashed（模擬 Worker 在送出後中止）。"""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.gate = asyncio.Event()
        self.gate.set()
        self.crash = False

    async def fetch_result(self, job: ProviderJob) -> ProviderResult:
        if self.crash:
            raise WorkerCrashed(job.external_id)
        await self.gate.wait()
        return await super().fetch_result(job)


class WorkerCrashed(BaseException):
    """模擬 Worker 行程被終止：不是 Exception，業務上的錯誤處理不會攔截。"""


class YieldingClock(FakeClock):
    """sleep 推進時鐘並讓出事件迴圈，讓並行的協程有機會執行。"""

    async def sleep(self, seconds: float) -> None:
        self.advance(seconds)
        await asyncio.sleep(0)


async def jobs_of_video(repos: Repositories, video_id: str) -> list[GenerationJob]:
    """影片所有鏡頭版本的生成工作（記憶體 repository）。"""
    found: list[GenerationJob] = []
    for shot in await repos.shots.list_shots(video_id):
        take_ids = {t.id for t in await repos.shots.takes(shot.id)}
        statuses = ("queued", "submitted", "running", "succeeded", "stored", "failed", "failed_final")
        found += [j for j in await repos.jobs.list_by_status(statuses) if j.shot_take_id in take_ids]
    return found
