# 片尾卡：設計

> 對應規格：spec.md（版本 v1）。本檔由 Claude Code 撰寫，隨規格核准一併審閱。

## 設計概要

```
backend/app/render/outro.py
├─ OutroInfo(name, address, primary_color, booking_url|None, logo: bytes|None)
├─ OutroCard(image: PIL.Image, layers: list[str], boxes: dict[str, (l, t, r, b)])
├─ parse_color(text) -> (r, g, b)              #RGB／#RRGGBB；錯誤 → ValueError（含原值）
├─ text_color(rgb) -> (r, g, b)                 WCAG 相對亮度 > 0.5 → 黑，否則白
├─ fit_text(draw, text, max_width, size, min_size, max_lines=2) -> (font, lines)
├─ make_card(info) -> OutroCard                 純運算
├─ outro_info(project, brand, storage) -> OutroInfo   由品牌檔案組出（讀 Logo）
└─ card_to_clip_command(png, mp4, seconds=3, fps=30) -> list[str]
```

### 版面（1080×1920，安全區：上 250、下 400、左右 80）

| 區塊 | 位置 | 內容 |
|---|---|---|
| Logo 區 | y 300–700，水平置中 | Logo 等比縮放到 ≤ 600×400；無 Logo 時改畫店名（字級 120，可縮至 72） |
| 店名 | y 760 起 | 字級 96，可縮至 48，最多 2 行；無 Logo 時此處不重複店名 |
| 地址 | 店名下方 40 px | 字級 48，可縮至 32，最多 2 行 |
| QR code | 地址下方 60 px，≥ 360×360，下緣不超過 y 1520 | 白底、quiet zone 4 格；`error_correction=M` |

`layers` 依實際繪製順序記錄：`background`、`logo`、`name`、`address`、`qr`；`boxes` 記錄每層的邊界框，供測試檢查安全區。

### 片尾影片段

`ffmpeg -loop 1 -i card.png -t 3 -r 30 -c:v libx264 -preset veryfast -tune stillimage -pix_fmt yuv420p -movflags +faststart outro.mp4`

### 編排串接

- `Renderer` 介面新增 `async def render_outro(info: OutroInfo, storage, key) -> None`；`FfmpegRenderer` 畫卡並轉影片段；`FakeRenderer` 寫入空檔。
- `_render`：`outro_info(...)` → `renderer.render_outro(info, storage, keys.outro(video.id))` → `build_timeline(..., outro_key=keys.outro(video.id))`。片尾產生與合成在同一個重試迴圈內（`RenderError`）。
- 沒有品牌檔案時（理論上不會發生）不加片尾。

## 資料模型／狀態轉換變更

無資料表變更。`keys.outro(video_id)`。新增依賴：`qrcode`、`opencv-python-headless`（dev）。

## API 契約（request／response、錯誤碼）

無。

## 失敗行為、安全與可觀測性

- 主色格式錯誤 → `ValueError`；在編排中轉為使用預設主色並記錄警告（避免整支影片因品牌色失敗）。
- Logo 讀取或解碼失敗 → 視為無 Logo，記錄警告。
- FFmpeg 失敗 → `RenderError`，由 S13 重試規則處理。

## 測試策略

| 需求 | 驗收條件 | 測試層級 | 測試位置 |
|---|---|---|---|
| R-001 | AC-001 | BDD（S14-01）＋Unit | `backend/tests/bdd/test_s14_outro.py`、`backend/tests/unit/test_outro.py` |
| R-002 | AC-002 | BDD（S14-02）＋Unit | 同上 |
| R-003 | AC-003 | BDD（S14-03）＋Unit | 同上 |
| R-004 | AC-004 | Unit | `backend/tests/unit/test_outro.py` |
| R-005 | AC-005 | Unit | 同上 |
| R-006 | AC-006 | BDD（S14-04）＋Unit | 同上 |
| R-007 | AC-007 | Unit | `backend/tests/unit/test_orchestrator_outro.py` |

- 測試 Logo：240×160 RGBA，填滿純藍 (0, 0, 255)，作為「獨特顏色」判斷 Logo 是否出現。
- QR 解碼：`cv2.QRCodeDetector().detectAndDecode`。
- 編排測試以 `FakeRenderer`（記錄 `render_outro` 呼叫）與會失敗的變體驗證，不執行 FFmpeg。

預計單元測試（≥ 2，預計約 18）：
- `test_r001_safe_area_for_all_layers`、`test_r001_logo_scaled_within_box`
- `test_r002_no_booking_url_skips_qr`、`test_r002_qr_min_size`
- `test_r003_broken_logo_treated_as_missing`、`test_r003_outro_info_reads_brand_profile`
- `test_r004_parse_color[…]`、`test_r004_parse_color_rejects[…]`、`test_r004_text_color_by_luminance[…]`
- `test_r005_long_name_shrinks_within_safe_area`、`test_r005_long_address_wraps`
- `test_r006_card_to_clip_command`
- `test_r007_outro_in_timeline`、`test_r007_outro_failure_retried`

## ADR（影響公開 API、資料遷移、成本、外部供應商或安全性時必填）

- 決定：片尾卡以 Pillow 繪製、`qrcode` 產生 QR，再以 FFmpeg 轉成靜態 3 秒影片段；每次合成重新產生。
- 替代方案：HTML 模板截圖；在主合成 filter graph 中直接疊圖。
- 取捨：Pillow 無需瀏覽器、可單元測試版面；獨立影片段讓時間軸維持「每段一個素材」的單純結構，代價是多一次 FFmpeg 執行（約 1 秒）。
