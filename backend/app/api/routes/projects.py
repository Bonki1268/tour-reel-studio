"""專案端點（spec 0008 R-002；spec 0015 R-007：具型別回應與圖片預簽名網址）。"""

from fastapi import APIRouter

from app.api.deps import Services
from app.api.schemas import BrandOut, CharacterOut, ProjectOut, ScenePhotoOut
from app.api.services import AppServices
from app.jobs.orchestrator import NotFound
from app.storage.objects import ObjectNotFound

router = APIRouter()


async def _url(svc: AppServices, key: str | None) -> str | None:
    """物件存在時回傳短期預簽名網址，否則 None。"""
    # S3 的預簽名不會檢查物件是否存在，先確認
    if not key or not await svc.storage.exists(key):
        return None
    try:
        return (await svc.storage.presign_get(key, svc.settings.presign_ttl_s)).url
    except ObjectNotFound:
        return None


@router.get("/projects/{project_id}")
async def get_project(project_id: str, svc: Services) -> ProjectOut:
    found = await svc.repos.projects.get(project_id)
    if found is None:
        raise NotFound(f"專案不存在：{project_id}")
    project, brand = found
    character = await svc.repos.characters.locked_version(project_id)
    photos = await svc.repos.scene_photos.list(project_id)
    return ProjectOut(
        id=project.id,
        name=project.name,
        brand=BrandOut(visual=brand.visual, selling_points=brand.selling_points, tone=brand.tone,
                       info=brand.info),
        character=None if character is None else CharacterOut(
            id=character.id, version=character.version, anchor_card=character.anchor_card,
            cutout_url=await _url(svc, character.cutout_key),
        ),
        scene_photos=[
            ScenePhotoOut(id=p.id, image_key=p.image_key, width=p.width, height=p.height,
                          description=p.description, url=await _url(svc, p.image_key))
            for p in photos
        ],
    )
