"""API 與 Worker 之間的工作佇列（spec 0008）：記憶體版供測試，arq（Redis）版供正式環境。"""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

JobHandler = Callable[[str, dict[str, Any]], Awaitable[None]]


class JobQueue(Protocol):
    async def enqueue(self, name: str, **kwargs: Any) -> None: ...


class MemoryJobQueue:
    """記錄排入的工作；run_all 依序執行（包含執行中新排入的工作），讓測試同步化 Worker。"""

    def __init__(self) -> None:
        self.jobs: list[tuple[str, dict[str, Any]]] = []
        self._next = 0

    async def enqueue(self, name: str, **kwargs: Any) -> None:
        raise NotImplementedError

    async def run_all(self, handler: JobHandler) -> None:
        raise NotImplementedError


class ArqJobQueue:
    def __init__(self, redis_url: str, *, queue_name: str | None = None) -> None:
        self.redis_url = redis_url
        self.queue_name = queue_name

    async def enqueue(self, name: str, **kwargs: Any) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError
