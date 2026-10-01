"""快速模式編排：主題 → 企劃 → 3 鏡平行生成 → 合成 → 成品確認（架構書 §5.2；spec 0007）。

狀態是否合法由領域層（S02 狀態機、S03 核准、S04 預算）判斷，本模組只負責順序與串接。
"""

import asyncio
import io
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from PIL import Image

from app.config import Settings
from app.creative.base import CreativeEngine, PlanContext, PlanDraft, ShotDraft
from app.domain.approval import (
    Approval,
    ApprovalKind,
    approve_plan,
    auto_approve,
    canonical_hash,
    plan_approval_input,
)
from app.domain.cost import Budget, CostTable, Estimate, JobKind, estimate_video
from app.domain.generation import JobStatus
from app.domain.ids import new_id
from app.domain.ports import Plan, Render, Repositories, Shot, ShotTake, Storage, VideoRecord
from app.domain.video import Video, VideoEvent, VideoStatus, utc_now
from app.jobs.events import EventPublisher, ProgressEvent
from app.jobs.generation import GenerationContext, JobSpec, run_generation_job
from app.providers.base import ImageProvider, ResultSource, VideoProvider
from app.providers.composite import Placement, PlacementError, build_compose_request, composite, to_png
from app.render.base import Renderer, RenderError
from app.render.outro import outro_info, parse_color
from app.render.timeline import Style
from app.storage import keys
from app.storage.objects import ObjectNotFound

PLAN_COUNT = range(2, 4)  # 創作引擎須提出 2～3 個企劃
ASPECT_RATIO = "9:16"
SUBTITLE_LANG = "zh-TW"
RENDER_ATTEMPTS = 2  # 合成失敗自動重試 1 次


class NotFound(KeyError):
    """專案、影片、企劃或鏡頭不存在（API 對應 404）。"""

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else "資料不存在"


class ShotAssetMissing(Exception):
    """B1 粗合成需要的實景照、角色去背圖或身份板不存在。"""


class PlanningFailed(Exception):
    """創作引擎失敗或企劃數不符；影片已進入 failed。"""

    def __init__(self, video_id: str, reason: str) -> None:
        self.video_id = video_id
        super().__init__(f"影片 {video_id} 企劃失敗：{reason}")


@dataclass
class OrchestratorDeps:
    repos: Repositories
    storage: Storage
    engine: CreativeEngine
    renderer: Renderer
    image_provider: ImageProvider
    video_provider: VideoProvider
    results: ResultSource
    events: EventPublisher
    cost_table: CostTable
    settings: Settings
    clock: Callable[[], datetime] = utc_now
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep


def _draft_from_payload(payload: Mapping[str, Any]) -> PlanDraft:
    return PlanDraft(**{**payload, "shots": [ShotDraft(**s) for s in payload["shots"]]})


def _approval_input(plan: Plan, shots: list[Shot]) -> object:
    """企劃核准涵蓋的內容：所選企劃＋各鏡目前的擺放（S03 plan_approval_input）。"""
    placements = [{"shot_no": s.shot_no, **(s.placement or {})} for s in shots]
    return plan_approval_input(plan.payload, placements)


class QuickModeOrchestrator:
    def __init__(self, deps: OrchestratorDeps) -> None:
        self.deps = deps
        self.repos = deps.repos

    # 企劃

    async def create_video(self, project_id: str, topic: str) -> VideoRecord:
        """建立快速模式影片並進入 planning（API 呼叫；企劃由 Worker 的 propose_plans 產生）。"""
        if await self.repos.projects.get(project_id) is None:
            raise NotFound(f"專案不存在：{project_id}")
        video = VideoRecord(
            id=new_id(), project_id=project_id, mode="quick", topic=topic, video=Video(clock=self.deps.clock)
        )
        await self.repos.videos.add(video)
        await self._apply(video, VideoEvent.SUBMIT_TOPIC)
        return video

    async def propose_plans(self, video_id: str) -> VideoRecord:
        """Worker：影片在 planning 時請創作引擎提出企劃，完成後進入 plan_ready。"""
        return await self._propose(await self._video(video_id))

    async def regenerate_plans(self, video_id: str) -> VideoRecord:
        video = await self._video(video_id)
        await self._apply(video, VideoEvent.REGENERATE_PLANS)
        return await self._propose(video)

    async def submit_topic(self, project_id: str, topic: str) -> VideoRecord:
        """建立影片並產生企劃（create_video＋propose_plans）。"""
        return await self._propose(await self.create_video(project_id, topic))

    async def _propose(self, video: VideoRecord) -> VideoRecord:
        try:
            drafts = await self.deps.engine.propose_plans(await self._plan_context(video))
            if len(drafts) not in PLAN_COUNT:
                raise ValueError(f"企劃數為 {len(drafts)}，應為 2～3 個")
        except Exception as e:
            await self._apply(video, VideoEvent.PLANNING_FAILED)
            await self._publish("planning_failed", video.id)
            raise PlanningFailed(video.id, str(e)) from e
        plan_ids = []
        for draft in drafts:
            plan = Plan(new_id(), video.id, asdict(draft), self.deps.engine.name)
            await self.repos.plans.add(plan)
            plan_ids.append(plan.id)
        await self._apply(video, VideoEvent.PLANS_READY)
        await self._publish("plan_ready", video.id, plan_ids=plan_ids)
        return video

    async def estimate(self, video_id: str, plan_id: str) -> Estimate:
        plan = await self._plan(video_id, plan_id)
        s = self.deps.settings
        return estimate_video(
            self.deps.cost_table, len(plan.payload["shots"]), s.hf_image_model, s.hf_video_model,
            s.retry_reserve_shots,
        )

    async def approve_plan(
        self, video_id: str, plan_id: str, cost_cap: Decimal, approved_by: str,
        placements: Mapping[int, Mapping[str, Any]] | None = None,
    ) -> Approval:
        video = await self._video(video_id)
        plan = await self._plan(video_id, plan_id)
        draft = _draft_from_payload(plan.payload)
        ctx = await self._plan_context(video)
        prompts = {p.shot_no: p for p in await self.deps.engine.build_shot_prompts(draft, ctx)}
        shots = [
            Shot(
                id=new_id(), video_id=video.id, shot_no=s.shot_no, role=s.role, duration_s=s.duration_s,
                scene_photo_id=s.scene_photo_id,
                placement=dict((placements or {}).get(s.shot_no, s.placement)),
                prompt={**asdict(prompts[s.shot_no]), "subtitle": s.subtitle},
            )
            for s in draft.shots
        ]
        approval = approve_plan(
            video.video, plan.payload, [{"shot_no": s.shot_no, **(s.placement or {})} for s in shots],
            cost_cap, approved_by,
        )
        video.selected_plan_id, video.cost_cap = plan.id, cost_cap
        await self.repos.videos.save(video)
        await self.repos.approvals.add(video.id, approval)
        for shot in shots:
            await self.repos.shots.add_shot(shot)
            await self.repos.shots.add_take(shot.id)
        # 快速模式自動採用：依企劃產生的腳本、使用的角色與實景照
        await self._auto_approve(video.id, ApprovalKind.SCRIPT, [s.prompt for s in shots])
        character = await self.repos.characters.locked_version(video.project_id)
        await self._auto_approve(video.id, ApprovalKind.ASSETS, {
            "character_version_id": character.id if character else None,
            "scene_photo_ids": [s.scene_photo_id for s in shots],
        })
        await self._publish("approved", video.id, kind=ApprovalKind.PLAN)
        return approval

    # 生成與合成

    async def generate(self, video_id: str) -> None:
        video = await self._video(video_id)
        shots = await self.repos.shots.list_shots(video_id)
        await self._generate(video, shots, shots)

    async def regenerate_shot(self, video_id: str, shot_no: int) -> None:
        video = await self._video(video_id)
        await self._apply(video, VideoEvent.REGENERATE_SHOT)
        shots = await self.repos.shots.list_shots(video_id)
        target = next(s for s in shots if s.shot_no == shot_no)
        await self.repos.shots.add_take(target.id)
        await self._generate(video, shots, [target])

    async def _generate(self, video: VideoRecord, all_shots: list[Shot], targets: list[Shot]) -> None:
        plan = await self._plan(video.id, video.selected_plan_id or "")
        approval = next(a for a in reversed(await self.repos.approvals.list(video.id))
                        if a.kind == ApprovalKind.PLAN)
        cap = approval.cost_cap or video.cost_cap or Decimal(0)
        gctx = GenerationContext(
            repos=self.repos, storage=self.deps.storage, image_provider=self.deps.image_provider,
            video_provider=self.deps.video_provider, results=self.deps.results,
            budget=Budget(cap=cap, entries=list(await self.repos.costs.list(video.id))),
            cost_table=self.deps.cost_table, settings=self.deps.settings,
            clock=self.deps.clock, sleep=self.deps.sleep,
        )
        approval_input = _approval_input(plan, all_shots)
        results = await asyncio.gather(
            *(self._run_shot(gctx, video, shot, approval, approval_input) for shot in targets),
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, BaseException):
                raise r  # 核准失效、超出預算等：所有鏡頭結束後才拋出
        if not all(results):
            await self._publish("needs_attention", video.id)
            return
        await self._apply(video, VideoEvent.ALL_SHOTS_DONE)
        await self._render(video)

    async def _run_shot(
        self, gctx: GenerationContext, video: VideoRecord, shot: Shot,
        approval: Approval, approval_input: object,
    ) -> bool:
        """關鍵幀 → 影片依序；回傳該鏡是否完成。"""
        take = await self._current_take(shot)
        prompt = shot.prompt or {}
        await self._publish("shot_started", video.id, shot.shot_no)
        try:
            keyframe_input = await self._prepare_keyframe(
                video, shot, take, prompt.get("keyframe_prompt", "")
            )
        except (PlacementError, ShotAssetMissing, ObjectNotFound) as e:
            # 擺放或素材有誤：不送出任何供應商請求，該鏡失敗（spec 0012 R-008）
            if video.video.status == VideoStatus.GENERATING:
                await self._apply(video, VideoEvent.SHOT_FAILED_FINAL)
            await self._publish("shot_failed", video.id, shot.shot_no, reason=str(e))
            return False
        keyframe = await run_generation_job(gctx, JobSpec(
            video, shot, take, JobKind.KEYFRAME, approval, approval_input, keyframe_input,
        ))
        if keyframe.status != JobStatus.STORED:
            await self._publish("shot_failed", video.id, shot.shot_no, job_id=keyframe.id)
            return False
        take = await self._current_take(shot)
        await self._auto_approve(video.id, ApprovalKind.KEYFRAMES,
                                 {"shot_no": shot.shot_no, "keyframe_key": take.keyframe_key})
        clip = await run_generation_job(gctx, JobSpec(
            video, shot, take, JobKind.VIDEO, approval, approval_input,
            {"shot_no": shot.shot_no, "prompt": prompt.get("video_prompt", ""),
             "keyframe_key": take.keyframe_key, "duration_s": shot.duration_s},
        ))
        if clip.status != JobStatus.STORED:
            await self._publish("shot_failed", video.id, shot.shot_no, job_id=clip.id)
            return False
        await self._publish("shot_done", video.id, shot.shot_no)
        return True

    async def _prepare_keyframe(
        self, video: VideoRecord, shot: Shot, take: ShotTake, keyframe_prompt: str
    ) -> dict[str, Any]:
        """B1：依擺放產生粗合成圖與遮罩並存入自有儲存，回傳精修合成請求（S11）作為關鍵幀工作輸入。"""
        placement = Placement.from_mapping(shot.placement or {})
        photo = next((p for p in await self.repos.scene_photos.list(video.project_id)
                      if p.id == shot.scene_photo_id), None)
        version = await self.repos.characters.locked_version(video.project_id)
        if photo is None or version is None or not version.cutout_key or not version.identity_board_key:
            raise ShotAssetMissing(f"第 {shot.shot_no} 鏡缺少實景照或已鎖定的角色素材")
        storage = self.deps.storage
        photo_bytes, cutout_bytes = await storage.get(photo.image_key), await storage.get(version.cutout_key)

        def render() -> tuple[bytes, bytes]:
            photo_img = Image.open(io.BytesIO(photo_bytes))
            result = composite(photo_img, Image.open(io.BytesIO(cutout_bytes)), placement)
            return to_png(result.rough), to_png(result.mask)

        rough_png, mask_png = await asyncio.to_thread(render)
        rough_key = keys.rough(video.id, shot.shot_no, take.attempt)
        mask_key = keys.mask(video.id, shot.shot_no, take.attempt)
        await storage.put(rough_key, rough_png, "image/png")
        await storage.put(mask_key, mask_png, "image/png")
        request = build_compose_request(
            rough_key=rough_key, mask_key=mask_key, identity_board_key=version.identity_board_key,
            keyframe_prompt=keyframe_prompt,
        )
        return {"shot_no": shot.shot_no, **request.to_input()}

    async def _render(self, video: VideoRecord) -> None:
        """產生片尾（S14）→ 依時間軸 JSON 合成；失敗自動重試 1 次，仍失敗則進入 needs_attention
        （架構書 §6.1；spec 0013、0014）。"""
        await self._publish("render_started", video.id)
        shots = await self.repos.shots.list_shots(video.id)
        pairs = [(s, await self._current_take(s)) for s in shots]
        found = await self.repos.projects.get(video.project_id)
        outro = await outro_info(found[0], found[1], self.deps.storage) if found else None
        style = Style(primary_color="#{:02X}{:02X}{:02X}".format(*parse_color(outro.primary_color))) \
            if outro else Style()
        outro_key = keys.outro(video.id) if outro else None
        bgm_key = self.deps.settings.bgm_key or None
        timeline = self.deps.renderer.build_timeline(
            video, pairs, style=style, outro_key=outro_key, bgm_key=bgm_key
        )
        video.timeline = timeline
        render = Render(new_id(), video.id, ASPECT_RATIO, "", SUBTITLE_LANG)
        render.mp4_key = keys.render(video.id, render.id)
        render.thumb_key = keys.render_thumb(video.id, render.id)
        for attempt in range(1, RENDER_ATTEMPTS + 1):
            try:
                if outro is not None and outro_key is not None:
                    await self.deps.renderer.render_outro(outro, self.deps.storage, outro_key)
                await self.deps.renderer.render(timeline, self.deps.storage, render.mp4_key, render.thumb_key)
                break
            except RenderError as e:
                if attempt < RENDER_ATTEMPTS:
                    await self._apply(video, VideoEvent.RENDER_RETRY)
                    continue
                await self._apply(video, VideoEvent.RENDER_FAILED_FINAL)
                await self._publish("render_failed", video.id, error=str(e)[:500])
                return
        await self.repos.renders.add(render)
        await self._apply(video, VideoEvent.RENDER_DONE)
        await self._publish("review_ready", video.id, render_id=render.id, mp4_key=render.mp4_key)

    # 成品確認

    async def approve_final(self, video_id: str, approved_by: str) -> Approval:
        video = await self._video(video_id)
        await self._apply(video, VideoEvent.APPROVE_FINAL)
        approval = Approval(
            ApprovalKind.FINAL, canonical_hash(video.timeline), None, False, approved_by, self.deps.clock()
        )
        await self.repos.approvals.add(video.id, approval)
        await self._publish("approved", video.id, kind=ApprovalKind.FINAL)
        return approval

    # 輔助

    async def _video(self, video_id: str) -> VideoRecord:
        video = await self.repos.videos.get(video_id)
        if video is None:
            raise NotFound(f"影片不存在：{video_id}")
        video.video.clock = self.deps.clock
        return video

    async def _plan(self, video_id: str, plan_id: str) -> Plan:
        plan = await self.repos.plans.get(plan_id)
        if plan is None or plan.video_id != video_id:
            raise NotFound(f"影片 {video_id} 沒有企劃 {plan_id}")
        return plan

    async def _plan_context(self, video: VideoRecord) -> PlanContext:
        project = await self.repos.projects.get(video.project_id)
        character = await self.repos.characters.locked_version(video.project_id)
        photos = await self.repos.scene_photos.list(video.project_id)
        if project is None or character is None or not photos:
            raise ValueError("專案缺少品牌檔案、已鎖定角色或實景照")
        return PlanContext(brand=project[1], topic=video.topic, anchor_card=character.anchor_card,
                           scene_photos=photos)

    async def _current_take(self, shot: Shot) -> ShotTake:
        current = await self.repos.shots.get_shot(shot.id)
        takes = await self.repos.shots.takes(shot.id)
        return next(t for t in takes if current is not None and t.id == current.current_take_id)

    async def _apply(self, video: VideoRecord, event: VideoEvent) -> VideoStatus:
        status = video.video.apply(event)
        await self.repos.videos.save(video)
        return status

    async def _auto_approve(self, video_id: str, kind: ApprovalKind, content: object) -> None:
        await self.repos.approvals.add(video_id, auto_approve(kind, content, clock=self.deps.clock))

    async def _publish(self, type_: str, video_id: str, shot_no: int | None = None, **data: Any) -> None:
        await self.deps.events.publish(ProgressEvent(type_, video_id, self.deps.clock(), shot_no, data))
