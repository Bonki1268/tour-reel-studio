"""V3 角色一致性：同一角色在 3 張實景照上連續生成 3 個鏡頭（企劃 s1 鉤子、s2 特色、s3 行動呼籲）。

輸入同 V2（inputs/brand.json 的 3 個鏡頭與 3 張實景照、character_cutout.png、可選 identity_board.png）。
首幀做法依 V2 的比較結果選擇：--mode raw（粗合成直接當首幀）或 --mode refined（Grok 精修）。

用法：
  poetry run python v3_consistency.py --mode refined           # 產生 3 張粗合成圖並估價
  poetry run python v3_consistency.py --mode refined --yes     # 實際生成（產生費用）
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
    ap.add_argument("--mode", choices=["raw", "refined"], required=True)
    opts = ap.parse_args()
    load_credentials()
    refine = opts.mode == "refined"

    brand = load_brand(default_brand())
    shots = build_plan(brand)["shots"]
    scenes = {s["id"]: s for s in brand["scenes"]}
    cutout = INPUTS / "character_cutout.png"
    identity = INPUTS / "identity_board.png"
    out = OUTPUTS / "v3"
    out.mkdir(parents=True, exist_ok=True)

    roughs, items = [], []
    for sh in shots:
        rough, _ = composite(INPUTS / scenes[sh["scene_photo_id"]]["file"], cutout, Placement(**sh["placement"]))
        rough.save(out / f"s{sh['shot_no']}-rough.png")
        roughs.append(rough)
        if refine:
            items.append((f"s{sh['shot_no']} 精修", IMAGE_MODEL, refine_args(PLACEHOLDER_URL, PLACEHOLDER_URL)))
        items.append((f"s{sh['shot_no']} I2V {sh['generate_duration_s']}s", I2V_MODEL,
                      i2v_args(PLACEHOLDER_URL, sh["video_prompt"], sh["generate_duration_s"])))
    print(f"V3 粗合成完成：{out}/s1–s3-rough.png（首幀：{opts.mode}）")
    ests = quote(items)
    if not opts.yes:
        print("只估價；請先檢查 3 張粗合成圖，加上 --yes 才會實際送出。")
        return

    client = make_client()
    identity_url = client.upload_file(identity if identity.exists() else cutout)
    per_shot = 2 if refine else 1
    failures = []
    for i, (sh, rough) in enumerate(zip(shots, roughs, strict=True)):
        print(f"— s{sh['shot_no']} {sh['role']}")
        e = ests[i * per_shot:(i + 1) * per_shot]
        try:
            run_shot(client, experiment="V3", label=f"s{sh['shot_no']}-{opts.mode}",
                     rough_url=upload_png(client, rough), identity_url=identity_url,
                     prompt=sh["video_prompt"], duration=sh["generate_duration_s"], refine=refine,
                     ests={"refine": e[0] if refine else None, "i2v": e[-1]}, out_dir=out)
        except GenerationFailed as err:
            print(f"  ✗ {err}")
            failures.append(sh["shot_no"])
    if failures:
        raise SystemExit(f"V3 未全部成功：鏡頭 {failures} 失敗（詳見 results/runs.jsonl）")
    print(f"V3 三鏡完成，檔案在 {out}；請並排觀看比較角色臉型、髮型、服裝與配色。")


if __name__ == "__main__":
    main()
