"""專案端點（spec 0008 R-002）。"""

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder

from app.api.deps import Services
from app.jobs.orchestrator import NotFound

router = APIRouter()


@router.get("/projects/{project_id}")
async def get_project(project_id: str, svc: Services) -> dict[str, Any]:
    found = await svc.repos.projects.get(project_id)
    if found is None:
        raise NotFound(f"專案不存在：{project_id}")
    project, brand = found
    character = await svc.repos.characters.locked_version(project_id)
    photos = await svc.repos.scene_photos.list(project_id)
    body = {
        "id": project.id,
        "name": project.name,
        "brand": asdict(brand),
        "character": None if character is None else {
            "id": character.id, "version": character.version, "anchor_card": character.anchor_card,
        },
        "scene_photos": [asdict(p) for p in photos],
    }
    return dict(jsonable_encoder(body))
