"""S08 測試共用：以 S07 的假實作、記憶體佇列與事件匯流排組成的 API 環境。"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx
from fastapi import FastAPI

from app.api.main import create_app
from app.api.services import AppServices
from app.jobs.queue import MemoryJobQueue
from app.jobs.worker import run_job
from tests.orchestration_support import OrchEnv


@dataclass
class ApiEnv:
    orch_env: OrchEnv = field(default_factory=OrchEnv)
    queue: MemoryJobQueue = field(default_factory=MemoryJobQueue)
    keepalive_s: float = 15
    _services: AppServices | None = None
    _app: FastAPI | None = None

    @property
    def services(self) -> AppServices:
        if self._services is None:
            env = self.orch_env
            settings = env.orch.deps.settings.model_copy(update={"sse_keepalive_s": self.keepalive_s})
            self._services = AppServices(
                settings=settings, repos=env.repos, storage=env.storage, orchestrator=env.orch,
                queue=self.queue, events=env.bus, clock=env.clock,
            )
        return self._services

    @property
    def app(self) -> FastAPI:
        if self._app is None:
            self._app = create_app(self.services.settings, self.services)
        return self._app

    @property
    def repos(self) -> Any:
        return self.orch_env.repos

    async def setup_project(self) -> str:
        return await self.orch_env.setup_project()

    async def request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kw)

    async def run_jobs(self) -> None:
        await self.queue.run_all(lambda name, kwargs: run_job(self.services, name, **kwargs))

    async def create_video(self, topic: str = "清晨採梅體驗") -> str:
        r = await self.request("POST", f"/projects/{self.orch_env.project_id}/videos", json={"topic": topic})
        assert r.status_code == 201, r.text
        return str(r.json()["id"])

    async def first_plan_body(self, video_id: str) -> dict[str, Any]:
        r = await self.request("GET", f"/videos/{video_id}")
        plan = r.json()["plans"][0]
        return {"plan_id": plan["id"], "cost_cap": plan["estimate"]["cap"]}

    async def approve_plan(self, video_id: str, key: str = "approve-1", **overrides: Any) -> httpx.Response:
        body = {**await self.first_plan_body(video_id), **overrides}
        return await self.request(
            "POST", f"/videos/{video_id}/approve-plan", json=body, headers={"Idempotency-Key": key}
        )

    async def video_in(self, status: str) -> str:
        """經由 API 與記憶體 Worker 把影片帶到指定狀態。"""
        video_id = await self.create_video()
        if status == "planning":
            return video_id
        await self.run_jobs()
        if status == "plan_ready":
            return video_id
        assert (await self.approve_plan(video_id)).status_code == 202
        if status == "generating":
            return video_id
        await self.run_jobs()
        if status == "review":
            return video_id
        assert (await self.request("POST", f"/videos/{video_id}/approve")).status_code == 200
        assert status == "approved"
        return video_id

    async def status(self, video_id: str) -> str:
        return str((await self.request("GET", f"/videos/{video_id}")).json()["status"])

    def queued(self, name: str) -> list[dict[str, Any]]:
        return [kw for n, kw in self.queue.jobs if n == name]


def as_decimal(value: Any) -> Decimal:
    return Decimal(str(value))
