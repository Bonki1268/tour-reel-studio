"""FakeProvider：以腳本決定每次送出的結果，供測試與 Demo 使用（spec 0006）。"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.providers.base import ProviderError, ProviderJob, ProviderRequest, ProviderResult

Outcome = Literal["succeed", "fail", "fail_non_retryable", "never"]

_CONTENT_TYPES = {"compose": "image/png", "image_to_video": "video/mp4"}


@dataclass
class _Submitted:
    outcome: Outcome
    operation: str
    polls: int = 0


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
        if not outcomes:
            raise ValueError("outcomes 至少要有一項")
        self.submissions: list[ProviderRequest] = []  # 每次送出的請求
        self.external_ids: list[str] = []  # 每次送出回傳的 request ID
        self.fetches: list[str] = []  # 每次查詢的 request ID
        self._outcomes = list(outcomes)
        self._running_polls = running_polls
        self._actual_cost = actual_cost
        self._content = content
        self._on_submit = on_submit
        self._name = name
        self._jobs: dict[str, _Submitted] = {}

    async def compose(self, req: ProviderRequest) -> ProviderJob:
        return self._submit(req, "compose")

    async def image_to_video(self, req: ProviderRequest) -> ProviderJob:
        return self._submit(req, "image_to_video")

    def _submit(self, req: ProviderRequest, operation: str) -> ProviderJob:
        self.submissions.append(req)
        if self._on_submit is not None:
            self._on_submit()
        n = len(self.submissions)
        external_id = f"{self._name}-req-{n}"
        self.external_ids.append(external_id)
        self._jobs[external_id] = _Submitted(self._outcomes[min(n, len(self._outcomes)) - 1], operation)
        return ProviderJob(provider=self._name, model=req.model, external_id=external_id)

    async def fetch_result(self, job: ProviderJob) -> ProviderResult:
        self.fetches.append(job.external_id)
        state = self._jobs[job.external_id]
        if state.outcome == "never" or state.polls < self._running_polls:
            state.polls += 1
            return ProviderResult("running")
        if state.outcome == "succeed":
            url = f"https://fake.example/{state.operation}/{job.external_id}"
            return ProviderResult("succeeded", url=url, actual_cost=self._actual_cost)
        retryable = state.outcome == "fail"
        return ProviderResult("failed", error=ProviderError("假供應商：生成失敗", retryable=retryable))

    async def download(self, result: ProviderResult) -> tuple[bytes, str]:
        if result.url is None:
            raise ProviderError("沒有結果可下載")
        operation = result.url.split("/")[-2]
        return self._content, _CONTENT_TYPES[operation]
