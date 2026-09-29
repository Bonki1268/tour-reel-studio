"""tourism-promo 模板（S00 手動版）：15 秒＝鉤子 4 秒＋特色 5 秒＋行動呼籲 3 秒＋片尾卡 3 秒。

輸出兩樣東西：
1. 企劃 JSON（架構書 §5.4 PlanDraft 格式），每鏡附圖生影片提示詞
2. 之後交給 Claude 產生企劃時使用的提示詞（PromptEngine 的雛形）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STRUCTURE = [
    # (role, 企劃秒數, 功能說明)
    ("hook", 4, "開場鉤子：角色在最有辨識度的實景中開場，前 1–2 秒就抓住注意力"),
    ("feature", 5, "特色展示：呈現選定的賣點"),
    ("cta", 3, "行動呼籲：角色邀請觀眾，接固定片尾卡"),
]
OUTRO_S = 3
SEEDANCE_MIN_S = 4  # Seedance 2.5 duration 下限；3 秒鏡頭需生成 4 秒後裁切

VIDEO_PROMPT = (
    "{anchor}. {action}. Setting: {scene}. Camera: {camera}. "
    "Keep the real background, buildings and landmarks exactly as in the first frame; "
    "consistent natural lighting and shadows; photorealistic; vertical 9:16; "
    "no on-screen text, no subtitles, no logos."
)


def load_brand(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_plan(brand: dict[str, Any]) -> dict[str, Any]:
    scenes = {s["id"]: s for s in brand["scenes"]}
    shots = []
    for (role, dur, _), s in zip(STRUCTURE, brand["shots"], strict=True):
        scene = scenes[s["scene_photo_id"]]
        shots.append({
            "shot_no": len(shots) + 1,
            "role": role,
            "duration_s": dur,
            "generate_duration_s": max(dur, SEEDANCE_MIN_S),
            "scene_photo_id": scene["id"],
            "placement": s["placement"],
            "action": s["action_zh"],
            "subtitle": s["subtitle"],
            "camera": s["camera"],
            "video_prompt": VIDEO_PROMPT.format(
                anchor=brand["character"]["anchor_en"], action=s["action_en"],
                scene=scene["description_en"], camera=s["camera_en"],
            ),
        })
    total = sum(sh["duration_s"] for sh in shots)
    assert total + OUTRO_S == 15, f"鏡頭合計 {total} 秒＋片尾 {OUTRO_S} 秒不等於 15 秒"
    return {
        "title": brand["plan"]["title"],
        "concept": brand["plan"]["concept"],
        "tone": brand["tone"],
        "shots": shots,
        "outro": {"duration_s": OUTRO_S, "shop": brand["name"], "address": brand["address"]},
        "cta": brand["cta"],
    }


def claude_prompt(brand: dict[str, Any], topic: str) -> str:
    """之後 PromptEngine 送給 Claude 的提示詞（S00 只產生、不呼叫）。"""
    photos = "\n".join(f"- {s['id']}：{s['description_zh']}" for s in brand["scenes"])
    rules = "\n".join(f"- s{i + 1} {role}：約 {d} 秒。{desc}" for i, (role, d, desc) in enumerate(STRUCTURE))
    return f"""你是觀光宣傳短片企劃。請為以下店家產生 3 個 IG Reels 15 秒企劃，輸出符合 JSON Schema 的 JSON，不要輸出其他文字。

## 固定結構（tourism-promo）
{rules}
- 片尾卡 {OUTRO_S} 秒由系統以模板產生（Logo、店名、地址、QR code），不必企劃。
- 三鏡秒數合計必須為 12 秒；字幕為繁體中文、每句 12 字以內；不生成對白與語音。

## 店家品牌檔案
- 店名：{brand['name']}
- 語氣：{brand['tone']}
- 賣點：{'、'.join(brand['selling_points'])}
- 地址：{brand['address']}
- 行動呼籲：{brand['cta']}

## 角色（已定妝，身份錨點不可變動）
{brand['character']['anchor_zh']}

## 可用實景照（每鏡只能從中選一張，填入 scene_photo_id）
{photos}

## 本支影片主題
{topic}

## 每鏡欄位
shot_no、role、duration_s、scene_photo_id、placement{{x,y,scale,flip}}（腳底中心位置與身高比例，0–1）、
action（繁中）、subtitle（繁中）、camera（繁中）、video_prompt（英文，描述角色動作與運鏡，並要求保留實景背景）
"""
