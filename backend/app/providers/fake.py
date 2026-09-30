"""FakeProvider：以腳本決定每次送出的結果，供測試與 Demo 使用（spec 0006）。"""

from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Literal

from app.providers.base import ProviderJob, ProviderRequest, ProviderResult

Outcome = Literal["succeed", "fail", "fail_non_retryable", "never"]


class FakeProvider:
    """同時實作 ImageProvider、VideoProvider、ResultSource。

    outcomes 依送出次數取用（超出時重複最後一項）；running_polls 為完成前回報 running 的次數；
    on_submit 在每次送出時呼叫（測試用來推進時鐘或模擬其他事件）。
    """

    def __init__(
        self,
        outcomes: Sequence[Outcome] = ("succeed",),
        *,
        running_polls: int = 1,
        actual_cost: Decimal | None = None,
        content: bytes = b"fake-result",
        on_submit: Callable[[], None] | None = None,
        name: str = "fake",
    ) -> None:
        self.submissions: list[ProviderRequest] = []  # 每次送出的請求
        self.external_ids: list[str] = []  # 每次送出回傳的 request ID
        self.fetches: list[str] = []  # 每次查詢的 request ID
        raise NotImplementedError

    async def compose(self, req: ProviderRequest) -> ProviderJob:
        raise NotImplementedError

    async def image_to_video(self, req: ProviderRequest) -> ProviderJob:
        raise NotImplementedError

    async def fetch_result(self, job: ProviderJob) -> ProviderResult:
        raise NotImplementedError

    async def download(self, result: ProviderResult) -> tuple[bytes, str]:
        raise NotImplementedError
