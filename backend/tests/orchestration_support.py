"""S07 測試共用：含品牌、已鎖定角色與 3 張實景照的專案，以及以假實作組成的編排環境。"""

from dataclasses import dataclass, field
from typing import Any

from app.config import Settings
from app.creative.fake import FakeCreativeEngine
from app.domain.cost import CostTable
from app.domain.ids import new_id
from app.domain.ports import Character, CharacterVersion, Repositories, ScenePhoto, Shot, ShotTake
from app.jobs.events import MemoryEventBus
from app.jobs.orchestrator import OrchestratorDeps, QuickModeOrchestrator
from app.providers.composite import to_png
from app.providers.fake import FakeProvider
from app.render.fake import FakeRenderer
from app.storage.memory_repos import memory_repositories
from app.storage.objects import MemoryStorage
from tests.composite_support import make_cutout, make_photo
from tests.generation_support import IMAGE_MODEL, KEYFRAME_PRICE, VIDEO_MODEL, VIDEO_PRICE, FakeClock
from tests.persistence_data import sample_project

ANCHOR_CARD = {"name": "梅子阿伯", "outfit": "藍色工作服、草帽", "age": 60}


@dataclass
class OrchEnv:
    provider: FakeProvider = field(default_factory=FakeProvider)
    engine: FakeCreativeEngine = field(default_factory=FakeCreativeEngine)
    renderer: FakeRenderer = field(default_factory=FakeRenderer)
    storage: MemoryStorage = field(default_factory=MemoryStorage)
    repos: Repositories = field(default_factory=memory_repositories)
    bus: MemoryEventBus = field(default_factory=MemoryEventBus)
    clock: FakeClock = field(default_factory=FakeClock)
    real_time: bool = False  # S07-02：以真實時間驗證平行度
    project_id: str = ""
    photos: list[ScenePhoto] = field(default_factory=list)
    _orch: QuickModeOrchestrator | None = None

    async def setup_project(self) -> str:
        project, brand = sample_project()
        await self.repos.projects.add(project, brand)
        character = Character(id=new_id(), project_id=project.id, name="梅子阿伯")
        version = CharacterVersion(
            id=new_id(), character_id=character.id, version=1, status="locked",
            identity_board_key="projects/p/characters/c/v1/identity_board.png",
            cutout_key="projects/p/characters/c/v1/cutout.png", anchor_card=ANCHOR_CARD,
        )
        character.locked_version_id = version.id
        await self.repos.characters.add(character, [version])
        self.photos = [
            ScenePhoto(id=new_id(), project_id=project.id, image_key=f"projects/p/scenes/{n}.jpg",
                       width=1080, height=1920, description=desc)
            for n, desc in enumerate(["梅園入口", "採梅步道", "梅子醋工坊"], start=1)
        ]
        for photo in self.photos:
            await self.repos.scene_photos.add(photo)
            await self.storage.put(photo.image_key, to_png(make_photo((108, 192))), "image/png")
        # B1 粗合成需要的素材（S12 起編排會讀取）
        await self.storage.put(version.cutout_key or "", to_png(make_cutout()), "image/png")
        await self.storage.put(version.identity_board_key or "", b"identity-board-png", "image/png")
        self.project_id = project.id
        return project.id

    @property
    def orch(self) -> QuickModeOrchestrator:
        if self._orch is None:
            table = CostTable.from_rows([
                {"kind": "keyframe", "model": IMAGE_MODEL, "credits": str(KEYFRAME_PRICE)},
                {"kind": "video", "model": VIDEO_MODEL, "credits": str(VIDEO_PRICE)},
            ])
            settings = Settings(
                hf_image_model=IMAGE_MODEL, hf_video_model=VIDEO_MODEL,
                generation_timeout_s=600, generation_poll_interval_s=0.05 if self.real_time else 0.2,
            )
            extra: dict[str, Any] = {} if self.real_time else {"clock": self.clock, "sleep": self.clock.sleep}
            self._orch = QuickModeOrchestrator(OrchestratorDeps(
                repos=self.repos, storage=self.storage, engine=self.engine, renderer=self.renderer,
                image_provider=self.provider, video_provider=self.provider, results=self.provider,
                events=self.bus, cost_table=table, settings=settings, **extra,
            ))
        return self._orch

    async def to_plan_ready(self, topic: str = "清晨採梅體驗") -> str:
        if not self.project_id:
            await self.setup_project()
        video = await self.orch.submit_topic(self.project_id, topic)
        return video.id

    async def approve_first_plan(self, video_id: str, **kw: Any) -> None:
        plans = await self.repos.plans.list(video_id)
        estimate = await self.orch.estimate(video_id, plans[0].id)
        await self.orch.approve_plan(video_id, plans[0].id, estimate.cap, "店長", **kw)

    async def to_review(self) -> str:
        video_id = await self.to_plan_ready()
        await self.approve_first_plan(video_id)
        await self.orch.generate(video_id)
        return video_id

    async def full_flow(self) -> str:
        video_id = await self.to_review()
        await self.orch.approve_final(video_id, "店長")
        return video_id

    async def shots(self, video_id: str) -> list[tuple[Shot, ShotTake | None]]:
        """每鏡與其目前版本。"""
        result = []
        for shot in await self.repos.shots.list_shots(video_id):
            takes = await self.repos.shots.takes(shot.id)
            result.append((shot, next((t for t in takes if t.id == shot.current_take_id), None)))
        return result

    async def shot_done(self, video_id: str, shot_no: int) -> bool:
        """該鏡目前版本的關鍵幀與影片都已存入物件儲存。"""
        for shot, take in await self.shots(video_id):
            if shot.shot_no == shot_no:
                return bool(
                    take and take.keyframe_key and take.clip_key
                    and await self.storage.exists(take.keyframe_key)
                    and await self.storage.exists(take.clip_key)
                )
        return False

    async def video_status(self, video_id: str) -> str:
        video = await self.repos.videos.get(video_id)
        assert video is not None
        return video.video.status

    async def status_trail(self, video_id: str) -> list[str]:
        video = await self.repos.videos.get(video_id)
        assert video is not None
        return list(video.video.status_trail)

    def event_types(self) -> list[str]:
        return [e.type for e in self.bus.events]


def is_subsequence(expected: list[str], actual: list[str]) -> bool:
    it = iter(actual)
    return all(any(a == e for a in it) for e in expected)
