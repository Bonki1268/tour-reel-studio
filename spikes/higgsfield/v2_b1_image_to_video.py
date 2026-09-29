"""V2 B1 照片合成＋圖生影片：同一張實景照、同一擺放，比較「粗合成直接當首幀」與「Grok 精修後當首幀」。

需要的輸入（放在 inputs/）：
  brand.json               由 brand.example.json 複製修改（取第 1 鏡的實景照、擺放與提示詞）
  character_cutout.png     角色去背全身圖（透明背景 PNG）
  identity_board.png       （可選）角色身份板；沒有時以去背圖作為精修參考
  scene 檔案                brand.json 中 scenes[].file 指定的實景照

用法：
  poetry run python v2_b1_image_to_video.py                    # 產生粗合成圖並估價
  poetry run python v2_b1_image_to_video.py --yes              # 實際生成（產生費用）
  poetry run python v2_b1_image_to_video.py --yes --only raw   # 只跑其中一種
"""

from hf_common import (
    I2V_MODEL, IMAGE_MODEL, INPUTS, OUTPUTS, GenerationFailed, base_parser, load_credentials,
    make_client, quote,
)
from b1 import Placement, composite
from pipeline import PLACEHOLDER_URL, i2v_args, refine_args, run_shot, upload_png
from tourism_promo import build_plan, load_brand
from v4_tourism_promo import default_brand


def main() -> None:
    ap = base_parser(__doc__)
    ap.add_argument("--only", choices=["raw", "refined"])
    opts = ap.parse_args()
    load_credentials()

    brand = load_brand(default_brand())
    shot = build_plan(brand)["shots"][0]
    scene = next(s for s in brand["scenes"] if s["id"] == shot["scene_photo_id"])
    cutout = INPUTS / "character_cutout.png"
    identity = INPUTS / "identity_board.png"
    out = OUTPUTS / "v2"
    out.mkdir(parents=True, exist_ok=True)

    rough, mask = composite(INPUTS / scene["file"], cutout, Placement(**shot["placement"]))
    rough.save(out / "rough.png")
    mask.save(out / "mask.png")
    print(f"V2 粗合成完成：{out / 'rough.png'}（擺放 {shot['placement']}）")

    variants = [opts.only] if opts.only else ["raw", "refined"]
    items = []
    if "refined" in variants:
        items.append(("精修 Grok Image 2.0", IMAGE_MODEL, refine_args(PLACEHOLDER_URL, PLACEHOLDER_URL)))
    for v in variants:
        items.append((f"I2V {v} {shot['generate_duration_s']}s", I2V_MODEL,
                      i2v_args(PLACEHOLDER_URL, shot["video_prompt"], shot["generate_duration_s"])))
    ests = quote(items)
    est_refine = ests[0] if "refined" in variants else None
    est_i2v = ests[-1]
    if not opts.yes:
        print("只估價；請先檢查 rough.png 的構圖，加上 --yes 才會實際送出。")
        return

    client = make_client()
    rough_url = upload_png(client, rough)
    identity_url = client.upload_file(identity if identity.exists() else cutout)
    failures = []
    for v in variants:
        print(f"— {v}")
        try:
            run_shot(client, experiment="V2", label=f"s1-{v}", rough_url=rough_url,
                     identity_url=identity_url, prompt=shot["video_prompt"],
                     duration=shot["generate_duration_s"], refine=(v == "refined"),
                     ests={"refine": est_refine, "i2v": est_i2v}, out_dir=out)
        except GenerationFailed as e:
            print(f"  ✗ {e}")
            failures.append(v)
    if failures:
        raise SystemExit(f"V2 未全部成功：{failures} 失敗（詳見 results/runs.jsonl）")
    print(f"V2 全部完成，檔案在 {out}")


if __name__ == "__main__":
    main()
