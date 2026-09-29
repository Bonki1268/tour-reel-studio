"""V0 角色定妝：以 Grok Image 2.0 生成寫實風格角色全身圖（純白背景），再於本機去背。

輸出：
  outputs/character/<request_id>.png   原始生成圖
  inputs/identity_board.png            原始白底全身圖（單一正面視角，作為精修參考）
  inputs/character_cutout.png          去背全身圖（供 B1 粗合成）

用法：
  poetry run python v0_character.py                 # 只估價
  poetry run python v0_character.py --yes           # 實際生成（產生費用）並去背
  poetry run python v0_character.py --cutout-only   # 不呼叫 API，只對既有的 identity_board.png 重新去背
"""

from __future__ import annotations

import shutil

from PIL import Image, ImageDraw, ImageFilter

from hf_common import (
    IMAGE_MODEL, INPUTS, OUTPUTS, GenerationFailed, base_parser, download, load_credentials,
    make_client, quote, run_generation,
)
from tourism_promo import load_brand
from v4_tourism_promo import default_brand

PROMPT = (
    "Photorealistic full-body photograph of {anchor}. "
    "Standing upright facing the camera with a warm, confident expression, arms relaxed at the sides. "
    "The entire body is visible from the top of the hat to the boots, centered with margin on all sides. "
    "Plain pure white seamless studio background, soft even studio lighting, no shadow on the background, "
    "no props, no text, no watermark. Realistic skin texture and fabric detail, 50mm lens."
)
SENTINEL = (255, 0, 255)
BG_THRESH = 70  # 與背景色的容許差異（RGB 三色版差異加總）；過大會吃掉膚色與白領口
NEAR_WHITE = 190  # 底部起點門檻：含淺灰接地陰影（底部只有靴子與袍子，不會誤刪）


def cutout_white_bg(img: Image.Image) -> Image.Image:
    """從四角 flood fill 找出相連的白色背景並設為透明；衣物內部的白色不受影響。"""
    rgb = img.convert("RGB")
    filled = rgb.copy()
    w, h = filled.size
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    # 腳邊被地面陰影包圍的白色區塊（如兩腳之間）：只在畫面底部 20% 取接近純白的點當起點，
    # 避免誤刪上半身的白色領口
    for y in range(int(h * 0.8), h, 8):
        for x in range(0, w, 8):
            if min(filled.getpixel((x, y))) >= NEAR_WHITE:
                seeds.append((x, y))
    for xy in seeds:
        if filled.getpixel(xy) != SENTINEL:
            ImageDraw.floodfill(filled, xy, SENTINEL, thresh=BG_THRESH)
    alpha = Image.new("L", (w, h), 255)
    px_f, px_a = filled.load(), alpha.load()
    for y in range(h):
        for x in range(w):
            if px_f[x, y] == SENTINEL:
                px_a[x, y] = 0
    # 收邊 1px 並柔化，去掉白邊
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1))
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def main() -> None:
    ap = base_parser(__doc__)
    ap.add_argument("--cutout-only", action="store_true")
    opts = ap.parse_args()
    board = INPUTS / "identity_board.png"

    if not opts.cutout_only:
        load_credentials()
        brand = load_brand(default_brand())
        args = {
            "prompt": PROMPT.format(anchor=brand["character"]["anchor_en"]),
            "aspect_ratio": "9:16",
            "resolution": "2k",
            "quality": "medium",
        }
        print("V0 角色定妝（Grok Image 2.0）")
        [est] = quote([("角色全身圖 2k 9:16", IMAGE_MODEL, args)])
        if not opts.yes:
            print("只估價；加上 --yes 才會實際送出。")
            return
        try:
            rec = run_generation(make_client(), experiment="V0", label="character", model=IMAGE_MODEL,
                                 arguments=args, est=est)
        except GenerationFailed as e:
            raise SystemExit(str(e))
        raw = download(rec["output_url"], OUTPUTS / "character" / f"{rec['request_id']}.png")
        Image.open(raw).convert("RGB").save(board)
        print(f"原始圖：{raw}")
    elif not board.exists():
        raise SystemExit(f"找不到 {board}")

    cut = cutout_white_bg(Image.open(board))
    bbox = cut.getchannel("A").getbbox()
    if bbox is None:
        raise SystemExit("去背失敗：整張圖都被判定為背景")
    cut.save(INPUTS / "character_cutout.png")
    # 檢查用：去背圖疊在灰底上，方便看白邊與缺角
    check = Image.new("RGBA", cut.size, (128, 128, 128, 255))
    check.alpha_composite(cut)
    (OUTPUTS / "character").mkdir(parents=True, exist_ok=True)
    check.convert("RGB").save(OUTPUTS / "character" / "cutout_check.jpg")
    shutil.copy(board, OUTPUTS / "character" / "identity_board.png")
    print(f"去背完成：{INPUTS / 'character_cutout.png'}（角色範圍 {bbox}）；"
          f"檢查圖 {OUTPUTS / 'character' / 'cutout_check.jpg'}")


if __name__ == "__main__":
    main()
