# B1 照片合成：設計

> 對應規格：spec.md（版本 v1）。本檔由 Claude Code 撰寫，隨規格核准一併審閱。

## 設計概要

```
backend/app/providers/composite.py
├─ Placement           擺放參數（x, y, scale, flip），from_mapping 驗證範圍
├─ PlacementError      擺放參數錯誤（ValueError 子類）
├─ CompositeResult     rough（RGB）、mask（L）、box（角色在照片中的 left, top, width, height，可能部分超出）
├─ composite(photo, cutout, placement) -> CompositeResult     純運算，輸入輸出皆為 PIL.Image
├─ to_png(image) -> bytes
├─ ComposeRequest      base_image_key、mask_key、reference_keys、prompt；to_input() -> dict
└─ build_compose_request(*, rough_key, mask_key, identity_board_key, keyframe_prompt) -> ComposeRequest
```

新增依賴：`pillow`。

### 合成演算法（沿用 S00 `b1.py`，去掉 9:16 裁切）

1. `photo = ImageOps.exif_transpose(photo).convert("RGB")`；`cutout = cutout.convert("RGBA")`
2. `bbox = cutout.getchannel("A").getbbox()`；`None` → `PlacementError("角色圖沒有不透明像素")`；`char = cutout.crop(bbox)`
3. `flip` → `ImageOps.mirror(char)`
4. `h = max(1, round(scale × photo_h))`；`w = max(1, round(char_w × h / char_h))`；`LANCZOS` 縮放
5. `left = round(x × photo_w − w / 2)`；`top = round(y × photo_h − h)`
6. 與照片沒有交集 → `PlacementError("角色完全在畫面外")`
7. `rough = photo.copy(); rough.paste(char, (left, top), char)`；`mask = Image.new("L", size, 0); mask.paste(char.getchannel("A"), (left, top))`（`paste` 自動裁切超出部分）

`Placement.from_mapping` 接受 S10 企劃的 `placement` dict；`x`、`y` ∈ [0, 1]、`scale` ∈ (0, 1]，錯誤訊息列出每個超出範圍的參數名稱。

### 精修提示詞（英文，S00 結論）

```
Blend the character into the photo so it looks naturally photographed on location.
Keep the background exactly unchanged: same buildings, landmarks, composition and framing.
Keep the character's position, size and pose from the base image; match the identity reference.
Match the lighting and shadows of the scene, add a natural contact shadow under the feet.
Photorealistic, no text, no logos.
Shot: {keyframe_prompt}
```

`ComposeRequest.to_input()` 回傳 `{"base_image_key", "mask_key", "reference_keys", "prompt"}`，作為 S06 `ProviderRequest.input`；S12 的 adapter 再轉成 Higgsfield 的欄位（網址、參數名稱）。

## 資料模型／狀態轉換變更

無。

## API 契約（request／response、錯誤碼）

無新端點。`PlacementError` 是領域錯誤；API 層的擺放驗證（S15 前端送出擺放參數時）沿用同一個 `Placement.from_mapping`，屆時再對應 HTTP 422。

## 失敗行為、安全與可觀測性

- 所有錯誤在產生任何圖片前拋出，不留下部分結果。
- 圖片解碼失敗（非圖片檔）由 Pillow 拋出 `PIL.UnidentifiedImageError`，不在本步驟轉換（上傳時已驗證格式）。
- 不連網、不寫入儲存、不記錄圖片內容。

## 測試策略

| 需求 | 驗收條件 | 測試層級 | 測試位置 |
|---|---|---|---|
| R-001 | AC-001、AC-002 | BDD（S11-01）＋Unit | `backend/tests/bdd/test_s11_b1_composite.py`、`backend/tests/unit/test_composite.py` |
| R-002 | AC-003 | BDD（S11-02）＋Unit | 同上 |
| R-003 | AC-004 | BDD（S11-03） | 同上 |
| R-004 | AC-005 | BDD（S11-04）＋Unit | 同上 |
| R-005 | AC-006 | BDD（S11-05）＋Unit | 同上 |
| R-006 | AC-007 | BDD（S11-06）＋Unit | 同上 |

測試圖片（`tests/composite_support.py`，程式產生）：
- 實景照：1000×1500 純色（例如 RGB(40, 120, 60)）
- 角色：400×800 RGBA，四周透明邊；中間不透明區塊左半紅、右半藍（驗證翻轉），邊緣一圈半透明（驗證遮罩的 alpha）
- 角色高度與腳底位置以遮罩的 bounding box 量測

預計單元測試（≥ 3，預計約 10）：
- `test_r001_scale_keeps_aspect_ratio`、`test_r001_pixels_outside_character_unchanged`、`test_r001_same_ratios_across_resolutions`、`test_r001_exif_orientation_applied`
- `test_r002_mask_matches_alpha`
- `test_r004_fully_outside_raises`、`test_r004_transparent_cutout_raises`、`test_r004_partial_outside_is_cropped`
- `test_r005_out_of_range_names_parameter[x|y|scale…]`
- `test_r006_prompt_template_keeps_background_and_lighting`、`test_r006_to_input_shape`

## ADR（影響公開 API、資料遷移、成本、外部供應商或安全性時必填）

- 決定：先以 Pillow 粗合成再交模型精修（架構書 §5.3），合成保持輸入照片尺寸，9:16 裁切在上游處理。
- 替代方案：讓模型依文字描述擺放角色；或在合成內同時裁成 9:16（S00 做法）。
- 取捨：粗合成讓構圖可控、可重現，並與 B2 共用介面；把裁切移出合成讓合成只有一個責任、與場景的尺寸要求一致，代價是上游必須保證照片已是目標比例。
