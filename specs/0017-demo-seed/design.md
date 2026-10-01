# Demo 種子資料：設計

> 對應規格：spec.md（版本 v1）。本檔由 Claude Code 撰寫，隨規格核准一併審閱。

## 設計概要

```
seed/
├─ demo/
│  ├─ demo.json            品牌、角色、實景照描述（schema 見下）
│  ├─ logo.png（可選）、identity_board.png、character_cutout.png、scene-*.jpg
└─ cache/
   └─ firecrawl-<domain>.json   {"fetched_at", "source": "firecrawl"|"manual", "branding": {...}, "metadata": {...}}

backend/app/seed/
├─ schema.py     SeedDemo、SeedCharacter、SeedScene（Pydantic）；validate_dir(path) -> (SeedDemo, list[問題])
├─ firecrawl.py  brand_from_firecrawl(payload) -> BrandPatch；load_cache(domain)；refresh(domain, api_key)（httpx，僅 --refresh-firecrawl）
├─ assets.py     prepare_scene(bytes) -> bytes（EXIF 轉正、ImageOps.fit 9:16、1080×1920 JPEG q=88）
│                prepare_cutout(bytes) -> bytes（RGBA、裁掉不透明範圍下方的透明邊）
│                content_id(bytes) -> str（sha256 前 16 碼）
└─ run.py        seed(demo_dir, cache_dir, repos, storage, *, refresh=False) -> SeedResult；main()
```

### demo.json

```json
{
  "name": "古堡 1624 咖啡館",
  "website": "https://example.com",
  "tone": "歷史趣味、輕鬆親切",
  "selling_points": ["…"],
  "address": "台南市安平區…",
  "booking_url": "https://…",
  "colors": ["#8B2E1F"],
  "logo": "logo.png",
  "character": {"name": "鄭成功", "anchor_zh": "…", "anchor_en": "…",
                "identity_board": "identity_board.png", "cutout": "character_cutout.png"},
  "scenes": [{"file": "scene-1.jpg", "description_zh": "…", "description_en": "…"}]
}
```

### 流程（run.seed）

1. `validate_dir`：schema、檔案存在、實景照 3–5 張、去背圖有透明背景；有問題 → `SeedError(problems)`，不寫入。
2. 品牌：`demo.json` 為基礎；快取存在時以 `brand_from_firecrawl` 補上 colors、logo URL、fonts（`demo.json` 有明確值者優先）。`--refresh-firecrawl` → 先嘗試更新快取，失敗則沿用舊快取並記錄。
3. 專案：`project_id = uuid5(...)`；不存在 → 新增 Project＋BrandProfile；存在 → 更新 BrandProfile（`confirmed_at` 設為執行時間）。
4. Logo：`keys.brand_logo(project_id)`，內容相同時不重新上傳。
5. 角色：`version_id = uuid5(project_id + 身份板雜湊 + 去背圖雜湊)`；不存在 → 新增版本（`version = 現有最大 + 1`，status `locked`）並設為 locked_version；物件依 `keys.identity_board`、`keys.cutout` 寫入。
6. 實景照：`photo_id = content_id(原檔)`；不存在 → 前處理、寫入 `keys.scene_photo(project_id, photo_id)`、新增 ScenePhoto（1080×1920）。
7. 印出專案 ID 與新增／沿用的項目數。

### Repository 補充

`ProjectRepository.update_brand(brand)`、`CharacterRepository.versions(project_id)`／`add_version(character_id, version, lock=True)`。記憶體與 SQL 版都實作（SQL 版走既有資料表，無遷移）。

## 資料模型／狀態轉換變更

無資料表變更。新增 repository 方法。

## API 契約（request／response、錯誤碼）

無新端點。CLI：`python -m app.seed.run [--demo-dir seed/demo] [--cache-dir seed/cache] [--refresh-firecrawl]`；結束代碼 0 成功、1 驗證失敗、2 執行錯誤。

## 失敗行為、安全與可觀測性

- 驗證失敗不寫入；寫入途中失敗（資料庫或儲存錯誤）回報並以非 0 結束，重跑即可補齊（冪等）。
- Firecrawl 金鑰只從 `FIRECRAWL_API_KEY` 讀取，不寫入快取與日誌。

## 測試策略

| 需求 | 驗收條件 | 測試層級 | 測試位置 |
|---|---|---|---|
| R-001、R-002、R-003 | AC-001 | BDD（S17-01，integration） | `backend/tests/bdd/test_s17_seed.py` |
| R-004 | AC-002 | BDD（S17-02，integration） | 同上 |
| R-005 | AC-003 | BDD（S17-03，integration）＋Unit | 同上、`backend/tests/unit/test_seed.py` |
| R-006 | AC-004 | BDD（S17-04，integration）＋Unit | 同上 |
| R-003 | AC-005 | Unit | `backend/tests/unit/test_seed.py` |
| R-007 | AC-006 | Unit | 同上 |

- `tests/seed_support.py`：在 `tmp_path` 產生 demo 目錄（程式產生的實景照、身份板、透明背景去背圖、Logo、`demo.json`）與快取檔。
- 整合測試使用 S05 的測試資料庫 fixture 與 S09 的 MinIO（每個測試使用獨立的物件前綴並清理）。
- Firecrawl 連線錯誤以 `respx` 模擬。

預計單元測試（≥ 1，預計約 12）：
- `test_r007_schema_*`、`test_r005_firecrawl_branding_to_brand`、`test_r005_refresh_failure_keeps_cache`、`test_r003_prepare_scene_*`、`test_r006_prepare_cutout_*`、`test_r001_project_id_is_stable`

## ADR（影響公開 API、資料遷移、成本、外部供應商或安全性時必填）

- 決定：種子資料以檔案＋腳本管理，自然鍵為 UUIDv5（專案名稱）與內容雜湊；Firecrawl 只透過快取檔使用，更新快取需明確旗標。
- 替代方案：SQL dump；每次執行都呼叫 Firecrawl；以遞增 ID 建立專案。
- 取捨：檔案化素材可審閱、可重現；快取避免現場網路與費用風險；固定 ID 讓前端設定簡單。代價是素材變更要重跑腳本，舊版本資料保留在資料庫中。
