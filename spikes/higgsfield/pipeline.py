"""單鏡流程：B1 粗合成 →（可選）Grok Image 2.0 精修 → Seedance 2.5 圖生影片。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

import higgsfield_client
from hf_common import I2V_MODEL, IMAGE_MODEL, OUTPUTS, download, run_generation

PLACEHOLDER_URL = "https://example.com/input.png"  # 只用於估價，不會送出生成

REFINE_PROMPT = (
    "Refine this photo composite into one seamless photograph. "
    "Image 1 is the base: keep the background, camera angle, composition, and the character's "
    "position, size and pose exactly the same. "
    "Image 2 is the character reference: keep the face, hair, outfit and colors identical to it. "
    "Unify lighting and shadows: match the scene's light direction and color temperature, "
    "add realistic contact shadows under the feet, remove cut-out edges. "
    "Photorealistic. Do not add text, logos or new objects."
)


def refine_args(rough_url: str, identity_url: str) -> dict[str, Any]:
    return {
        "prompt": REFINE_PROMPT,
        "image_urls": [rough_url, identity_url],
        "aspect_ratio": "9:16",
        "resolution": "1k",
        "quality": "medium",
    }


def i2v_args(image_url: str, prompt: str, duration: int) -> dict[str, Any]:
    return {
        "image_url": image_url,
        "prompt": prompt,
        "duration": duration,
        "resolution": "720p",
        "output_format": "mp4",
        "generate_audio": False,  # 架構書 §5.5
    }


def upload_png(client: higgsfield_client.SyncClient, img: Image.Image) -> str:
    return client.upload_image(img, format="png")


def run_shot(
    client: higgsfield_client.SyncClient,
    *,
    experiment: str,
    label: str,
    rough_url: str,
    identity_url: str,
    prompt: str,
    duration: int,
    refine: bool,
    ests: dict[str, dict[str, Any]],
    out_dir: Path,
) -> dict[str, Any]:
    """回傳 {'keyframe': 精修紀錄或 None, 'video': 影片紀錄}；任何一步失敗即拋出 GenerationFailed。"""
    keyframe = None
    first_frame = rough_url
    if refine:
        keyframe = run_generation(client, experiment=experiment, label=f"{label}-refine",
                                  model=IMAGE_MODEL, arguments=refine_args(rough_url, identity_url),
                                  est=ests.get("refine"))
        first_frame = keyframe["output_url"]
        download(first_frame, out_dir / f"{label}-keyframe.png")
    video = run_generation(client, experiment=experiment, label=f"{label}-i2v", model=I2V_MODEL,
                           arguments=i2v_args(first_frame, prompt, duration), est=ests.get("i2v"))
    download(video["output_url"], out_dir / f"{label}.mp4")
    return {"keyframe": keyframe, "video": video}


__all__ = ["OUTPUTS", "PLACEHOLDER_URL", "i2v_args", "refine_args", "run_shot", "upload_png"]
