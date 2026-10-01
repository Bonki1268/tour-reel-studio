"""影片端點（spec 0008）：路由只做驗證、冪等與呼叫編排服務；狀態是否合法由領域層判斷。"""

import json
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import DEMO_USER, Services
from app.api.errors import CostCapTooLow, InvalidState
from app.api.idempotency import idempotent
from app.api.schemas import (
    ApprovePlanIn,
    DownloadOut,
    EstimateOut,
    PlanOut,
    RegenerateIn,
    ShotOut,
    TakeOut,
    TopicIn,
    VideoOut,
)
from app.api.services import AppServices
from app.api.sse import sse_stream
from app.domain.cost import CostTableError, JobKind
from app.domain.fallback import fallback_due
from app.domain.ports import VideoRecord
from app.domain.video import VideoEvent, VideoStatus, check_transition
from app.jobs.orchestrator import NotFound

router = APIRouter()


async def _video(svc: AppServices, video_id: str) -> VideoRecord:
    video = await svc.repos.videos.get(video_id)
    if video is None:
        raise NotFound(f"影片不存在：{video_id}")
    return video


def _shot_cost(svc: AppServices) -> Decimal:
    """單鏡完整重生（關鍵幀＋影片）的預估點數（與 S04 estimate_video 的單鏡成本相同）。"""
    table, s = svc.orchestrator.deps.cost_table, svc.settings
    try:
        return table.price(JobKind.KEYFRAME, s.hf_image_model) + table.price(JobKind.VIDEO, s.hf_video_model)
    except CostTableError:
        return Decimal(0)


async def video_out(svc: AppServices, video_id: str) -> VideoOut:
    video = await _video(svc, video_id)
    plans = [
        PlanOut(id=p.id, payload=p.payload,
                estimate=EstimateOut(**vars(await svc.orchestrator.estimate(video.id, p.id))))
        for p in await svc.repos.plans.list(video.id)
    ]
    regen_cost = _shot_cost(svc)
    shots = []
    for shot in await svc.repos.shots.list_shots(video.id):
        take = next((t for t in await svc.repos.shots.takes(shot.id) if t.id == shot.current_take_id), None)
        shots.append(ShotOut(
            shot_no=shot.shot_no, role=shot.role, duration_s=shot.duration_s, placement=shot.placement,
            take=None if take is None else TakeOut(attempt=take.attempt, status=take.status,
                                                   keyframe_key=take.keyframe_key, clip_key=take.clip_key),
            regen_cost=regen_cost,
        ))
    spent = sum((c.credits for c in await svc.repos.costs.list(video.id)), Decimal(0))
    renders = await svc.repos.renders.list(video.id)
    preview = None
    if renders:
        preview = (await svc.storage.presign_get(renders[-1].mp4_key, svc.settings.presign_ttl_s)).url
    return VideoOut(
        id=video.id, project_id=video.project_id, status=video.video.status, topic=video.topic, plans=plans,
        selected_plan_id=video.selected_plan_id, shots=shots, cost_cap=video.cost_cap, spent=spent,
        preview_url=preview, fallback_url=await _fallback_url(svc, video, has_render=bool(renders)),
    )


async def _fallback_url(svc: AppServices, video: VideoRecord, *, has_render: bool) -> str | None:
    """保底成品（spec 0018 R-006）：已設定、物件存在且生成超過展示門檻時回傳預簽名網址；不改變任何狀態。"""
    s = svc.settings
    key = s.demo_fallback_video.strip()
    if not key or not fallback_due(video.video, svc.clock(), s.demo_fallback_after_s, has_render=has_render):
        return None
    if not await svc.storage.exists(key):
        return None
    return (await svc.storage.presign_get(key, s.presign_ttl_s)).url


def _json(model: VideoOut) -> dict[str, Any]:
    return dict(json.loads(model.model_dump_json()))


@router.post("/projects/{project_id}/videos", status_code=201)
async def create_video(project_id: str, body: TopicIn, svc: Services) -> VideoOut:
    video = await svc.orchestrator.create_video(project_id, body.topic)
    await svc.queue.enqueue("plan_video", video_id=video.id)
    return await video_out(svc, video.id)


@router.get("/videos/{video_id}")
async def get_video(video_id: str, svc: Services) -> VideoOut:
    return await video_out(svc, video_id)


@router.post("/videos/{video_id}/plans/regenerate", status_code=202)
async def regenerate_plans(video_id: str, svc: Services) -> VideoOut:
    video = await _video(svc, video_id)
    check_transition(video.video.status, VideoEvent.REGENERATE_PLANS)
    await svc.queue.enqueue("regenerate_plans", video_id=video_id)
    return await video_out(svc, video_id)


@router.post("/videos/{video_id}/approve-plan", status_code=202)
async def approve_plan(
    video_id: str, body: ApprovePlanIn, svc: Services,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> JSONResponse:
    async def action() -> dict[str, Any]:
        estimate = await svc.orchestrator.estimate(video_id, body.plan_id)
        if body.cost_cap < estimate.total:
            raise CostCapTooLow(f"成本上限 {body.cost_cap} 點低於本次生成預估 {estimate.total} 點")
        placements = {n: p.model_dump() for n, p in body.placements.items()} if body.placements else None
        await svc.orchestrator.approve_plan(video_id, body.plan_id, body.cost_cap, DEMO_USER, placements)
        await svc.queue.enqueue("generate_video", video_id=video_id)
        return _json(await video_out(svc, video_id))

    request_body = json.loads(body.model_dump_json())
    return await idempotent(svc, f"approve-plan:{video_id}:{idempotency_key}", request_body, 202, action)


@router.post("/videos/{video_id}/shots/{shot_no}/regenerate", status_code=202)
async def regenerate_shot(
    video_id: str, shot_no: int, svc: Services, body: RegenerateIn | None = None
) -> VideoOut:
    video = await _video(svc, video_id)
    check_transition(video.video.status, VideoEvent.REGENERATE_SHOT)
    if shot_no not in {s.shot_no for s in await svc.repos.shots.list_shots(video_id)}:
        raise NotFound(f"影片 {video_id} 沒有第 {shot_no} 鏡")
    if body is not None and body.cost_cap is not None:
        # 使用者在確認對話框同意提高成本上限（spec 0016 R-007）
        await svc.orchestrator.raise_cost_cap(video_id, body.cost_cap, DEMO_USER)
    await svc.queue.enqueue("regenerate_shot", video_id=video_id, shot_no=shot_no)
    return await video_out(svc, video_id)


@router.post("/videos/{video_id}/approve")
async def approve_final(video_id: str, svc: Services) -> VideoOut:
    await svc.orchestrator.approve_final(video_id, DEMO_USER)
    return await video_out(svc, video_id)


@router.get("/videos/{video_id}/download")
async def download(video_id: str, svc: Services) -> DownloadOut:
    video = await _video(svc, video_id)
    renders = await svc.repos.renders.list(video_id)
    if video.video.status != VideoStatus.APPROVED or not renders:
        raise InvalidState("成品確認後才能下載")
    url = await svc.storage.presign_get(renders[-1].mp4_key, svc.settings.presign_ttl_s)
    return DownloadOut(url=url.url, expires_at=url.expires_at)


@router.get("/videos/{video_id}/events")
async def events(video_id: str, request: Request, svc: Services) -> StreamingResponse:
    await _video(svc, video_id)
    return StreamingResponse(
        sse_stream(svc, video_id, request.is_disconnected),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
