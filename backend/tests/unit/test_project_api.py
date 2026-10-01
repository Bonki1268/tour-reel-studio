"""GET /projects/{id} 具型別回應與預簽名網址（spec 0015 R-007）。"""

import pytest

from app.api.main import create_app
from tests.api_support import ApiEnv

pytestmark = pytest.mark.S15


@pytest.fixture
async def env() -> ApiEnv:
    env = ApiEnv()
    await env.setup_project()
    return env


async def test_r007_project_has_presigned_urls(env: ApiEnv) -> None:
    r = await env.request("GET", f"/projects/{env.orch_env.project_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "梅子農場"
    assert "手工梅子醋" in body["brand"]["selling_points"]
    version = await env.repos.characters.locked_version(env.orch_env.project_id)
    cutout_url = body["character"]["cutout_url"]
    assert cutout_url.startswith(f"memory://{version.cutout_key}?expires=")
    photos = body["scene_photos"]
    assert len(photos) == 3
    for photo, expected in zip(photos, env.orch_env.photos, strict=True):
        assert photo["id"] == expected.id
        assert photo["url"].startswith(f"memory://{expected.image_key}?expires=")
        assert (photo["width"], photo["height"]) == (expected.width, expected.height)


async def test_r007_missing_objects_null(env: ApiEnv) -> None:
    storage = env.orch_env.storage
    version = await env.repos.characters.locked_version(env.orch_env.project_id)
    storage._objects.pop(version.cutout_key)
    storage._objects.pop(env.orch_env.photos[0].image_key)
    body = (await env.request("GET", f"/projects/{env.orch_env.project_id}")).json()
    assert body["character"]["cutout_url"] is None
    assert body["scene_photos"][0]["url"] is None
    assert body["scene_photos"][1]["url"] is not None


async def test_r007_unknown_project_is_404(env: ApiEnv) -> None:
    r = await env.request("GET", "/projects/nope")
    assert r.status_code == 404


def test_r007_openapi_declares_project_out() -> None:
    schema = create_app(ApiEnv().services.settings, ApiEnv().services).openapi()
    responses = schema["paths"]["/projects/{project_id}"]["get"]["responses"]
    response = responses["200"]["content"]["application/json"]
    assert response["schema"]["$ref"].endswith("/ProjectOut")
    photo = schema["components"]["schemas"]["ScenePhotoOut"]["properties"]
    assert {"url", "width", "height"} <= set(photo)
