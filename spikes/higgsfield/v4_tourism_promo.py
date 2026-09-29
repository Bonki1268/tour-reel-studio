"""V4 tourism-promo 企劃與提示詞（不呼叫任何 API、不產生費用）。

用法：poetry run python v4_tourism_promo.py [--brand inputs/brand.json]
輸出：results/v4_plan.json、results/v4_claude_prompt.md
"""

import argparse
import json
from pathlib import Path

from hf_common import HERE, INPUTS
from tourism_promo import build_plan, claude_prompt, load_brand


def default_brand() -> Path:
    real = INPUTS / "brand.json"
    return real if real.exists() else HERE / "brand.example.json"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--brand", type=Path, default=default_brand())
    opts = p.parse_args()
    brand = load_brand(opts.brand)
    plan = build_plan(brand)
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / "v4_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "v4_claude_prompt.md").write_text(claude_prompt(brand, brand["topic"]), encoding="utf-8")
    print(f"品牌資料：{opts.brand}")
    for sh in plan["shots"]:
        print(f"s{sh['shot_no']} {sh['role']} {sh['duration_s']}s（生成 {sh['generate_duration_s']}s）"
              f" {sh['scene_photo_id']}｜{sh['subtitle']}\n  {sh['video_prompt']}")
    print(f"已寫入 {out / 'v4_plan.json'}、{out / 'v4_claude_prompt.md'}")


if __name__ == "__main__":
    main()
