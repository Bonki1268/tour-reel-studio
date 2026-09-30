"""FakeProvider：以腳本決定每次送出的結果，供測試與 Demo 使用（spec 0006）。"""

import time
from collections.abc import Callable, Mapping, Sequence
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
    submitted_at: float
    polls: int = 0


class FakeProvider:
    """同時實作 ImageProvider、VideoProvider、ResultSource。

    outcomes 依送出次數取用（超出時重複最後一項）；running_polls 為完成前回報 running 的次數；
    on_submit 在每次送出時呼叫（測試用來推進時鐘或模擬其他事件）；
    duration_s 為每個工作自送出起的真實耗時（time.monotonic）；
    outcomes_by_shot 依請求輸入的 shot_no 另外指定結果（各鏡分開計算送出次數）。
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
        duration_s: float = 0,
        outcomes_by_shot: Mapping[int, Sequence[Outcome]] | None = None,
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
        self._duration_s = duration_s
        self._by_shot = {k: list(v) for k, v in (outcomes_by_shot or {}).items()}
        self._shot_counts: dict[int, int] = {}

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
        self._jobs[external_id] = _Submitted(self._next_outcome(req, n), operation, time.monotonic())
        return ProviderJob(provider=self._name, model=req.model, external_id=external_id)

    def _next_outcome(self, req: ProviderRequest, n: int) -> Outcome:
        shot_no = req.input.get("shot_no")
        if isinstance(shot_no, int) and shot_no in self._by_shot:
            count = self._shot_counts[shot_no] = self._shot_counts.get(shot_no, 0) + 1
            outcomes = self._by_shot[shot_no]
            return outcomes[min(count, len(outcomes)) - 1]
        return self._outcomes[min(n, len(self._outcomes)) - 1]

    async def fetch_result(self, job: ProviderJob) -> ProviderResult:
        self.fetches.append(job.external_id)
        state = self._jobs[job.external_id]
        busy = time.monotonic() - state.submitted_at < self._duration_s
        if state.outcome == "never" or state.polls < self._running_polls or busy:
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
