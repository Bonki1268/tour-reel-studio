"""S06 測試共用：假時鐘、生成工作的測試環境。"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.config import Settings
from app.domain.approval import approve_plan, plan_approval_input
from app.domain.cost import Budget, CostTable, JobKind
from app.domain.ids import new_id
from app.domain.ports import GenerationJob, Repositories, Shot, ShotTake, VideoRecord
from app.domain.video import Video, VideoEvent
from app.jobs.generation import GenerationContext, JobSpec, run_generation_job
from app.providers.fake import FakeProvider
from app.storage.memory_repos import memory_repositories
from app.storage.objects import MemoryStorage
from tests.persistence_data import sample_project

IMAGE_MODEL = "img-model-a"
VIDEO_MODEL = "vid-model-a"
KEYFRAME_PRICE = Decimal("1.5")
VIDEO_PRICE = Decimal("4")

PLAN = {"title": "梅子季限定", "shots": [{"shot_no": 1, "action": "揮手"}, {"shot_no": 2, "action": "品嚐"}]}
PLACEMENTS = [{"shot_no": 1, "x": 0.4, "y": 0.8}, {"shot_no": 2, "x": 0.6, "y": 0.7}]


class FakeClock:
    """sleep 只推進時鐘，不實際等待。"""

    def __init__(self, start: datetime = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)

    async def sleep(self, seconds: float) -> None:
        self.advance(seconds)


@dataclass
class GenEnv:
    provider: FakeProvider = field(default_factory=FakeProvider)
    clock: FakeClock = field(default_factory=FakeClock)
    timeout_s: float = 600
    poll_interval_s: float = 0.2
    cap: Decimal = Decimal("100")
    modify_after_approval: bool = False
    repos: Repositories = field(default_factory=memory_repositories)
    storage: MemoryStorage = field(default_factory=MemoryStorage)
    ctx: GenerationContext | None = None
    video: VideoRecord | None = None
    shot: Shot | None = None
    take: ShotTake | None = None

    def settings(self) -> Settings:
        return Settings(
            hf_image_model=IMAGE_MODEL,
            hf_video_model=VIDEO_MODEL,
            generation_timeout_s=self.timeout_s,
            generation_poll_interval_s=self.poll_interval_s,
        )

    async def setup(self) -> GenerationContext:
        """建立已核准企劃、狀態為 generating 的影片與第 1 鏡。"""
        project, brand = sample_project()
        await self.repos.projects.add(project, brand)
        video = Video(clock=self.clock)
        video.apply(VideoEvent.SUBMIT_TOPIC)
        video.apply(VideoEvent.PLANS_READY)
        self.approval = approve_plan(video, PLAN, PLACEMENTS, self.cap, "店長")
        self.video = VideoRecord(
            id=new_id(), project_id=project.id, mode="quick", topic="梅子季限定",
            video=video, cost_cap=self.cap,
        )
        await self.repos.videos.add(self.video)
        self.shot = Shot(id=new_id(), video_id=self.video.id, shot_no=1, role="hook", duration_s=5.0)
        await self.repos.shots.add_shot(self.shot)
        self.take = await self.repos.shots.add_take(self.shot.id)
        table = CostTable.from_rows([
            {"kind": "keyframe", "model": IMAGE_MODEL, "credits": str(KEYFRAME_PRICE)},
            {"kind": "video", "model": VIDEO_MODEL, "credits": str(VIDEO_PRICE)},
        ])
        self.ctx = GenerationContext(
            repos=self.repos, storage=self.storage, image_provider=self.provider,
            video_provider=self.provider, results=self.provider, budget=Budget(cap=self.cap),
            cost_table=table, settings=self.settings(), clock=self.clock, sleep=self.clock.sleep,
        )
        return self.ctx

    def spec(self, kind: JobKind, *, snapshot: dict[str, Any] | None = None,
             take: ShotTake | None = None) -> JobSpec:
        assert self.video is not None and self.shot is not None and self.take is not None
        placements = [dict(p) for p in PLACEMENTS]
        if self.modify_after_approval:
            placements[0]["x"] = 0.1  # 第 1 鏡的擺放在核准後被修改
        return JobSpec(
            video=self.video, shot=self.shot, take=take or self.take, kind=kind, approval=self.approval,
            approval_input=plan_approval_input(PLAN, placements),
            input_snapshot=snapshot or {"prompt": "梅子園晨光", "shot_no": 1},
        )

    async def run(self, kind: JobKind, **spec_kw: Any) -> GenerationJob:
        ctx = self.ctx or await self.setup()
        return await run_generation_job(ctx, self.spec(kind, **spec_kw))

    async def attempts(self) -> list[GenerationJob]:
        """依事件順序取得所有嘗試（每個 job 一筆）。"""
        assert self.ctx is not None
        ids = list(dict.fromkeys(e.job_id for e in self.ctx.events))
        jobs = [await self.repos.jobs.get(i) for i in ids]
        return [j for j in jobs if j is not None]

    def statuses(self, attempt: int) -> list[str]:
        assert self.ctx is not None
        return [e.status for e in self.ctx.events if e.attempt == attempt]

    async def video_status(self) -> str:
        assert self.video is not None
        loaded = await self.repos.videos.get(self.video.id)
        assert loaded is not None
        return loaded.video.status


def keyframe_key(env: GenEnv) -> str:
    assert env.video is not None and env.take is not None
    return f"videos/{env.video.id}/shots/1/take{env.take.attempt}/keyframe.png"


JOB_KINDS = {"關鍵幀": JobKind.KEYFRAME, "影片": JobKind.VIDEO}
