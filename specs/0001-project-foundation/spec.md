# 開發骨架與設定載入

狀態：approved
版本：v1
關聯開發步驟：S01
核准者／時間：bonki

<!--
規則（spec-driven-development.md §4.1）：
- 「狀態」「核准者／時間」只能由使用者修改；Claude Code 只能產生 draft。
- 需求格式：- R-001：<使用者可觀察的行為>
- 驗收條件格式：- AC-001（對應 R-001）：Given / When / Then 或可量測條件
- 「驗收對應」把每個 AC 對應到 features/ 中本步驟的場景編號；本步驟每個非 external 場景都必須被至少一個 AC 對應。
- 自檢：python3 scripts/tdd.py spec
-->

## 問題與目標

之後 S02–S19 的每一步都要在同一套後端專案與測試設定上累積測試。本步驟建立：

- 可執行的 FastAPI 後端骨架與健康檢查端點
- 以環境變數載入的系統設定：開發與測試不需要任何金鑰；正式環境缺少必要金鑰時拒絕啟動
- 模型名稱與成本單價表路徑只由設定決定（架構書 §5.5、§9.2），程式中不寫死
- pytest＋pytest-bdd 測試設定、步驟 marker 與 ruff，讓 `scripts/tdd.py red／gate` 可以運作

## 範圍內／範圍外

**範圍內**
- `backend/pyproject.toml`（Poetry）、pytest／ruff／mypy 設定
- 目錄骨架 `backend/app/{api,domain,creative,providers,render,jobs,storage,seed}`、`backend/tests/{unit,bdd}`
- `backend/app/config.py`：`Settings` 與 `load_settings()`
- `backend/app/api/main.py`：FastAPI app 與 `GET /health`
- repo 根目錄的 `.env.example`，並確認 `.gitignore` 排除 `.env`、`.env.*`（保留 `.env.example`）

**範圍外**
- 資料庫、Redis、物件儲存的連線設定與健康檢查（S05、S06、S09 各自加入）
- 單價表檔案的內容與解析（S04）；本步驟只載入路徑
- 驗證金鑰是否有效（S10、S12 以 `@external` 驗證）
- docker-compose、CI、前端專案

## 使用者旅程

本步驟的使用者是開發者與維運者：

1. 開發者 clone repo 後執行 `poetry install`，不設定任何金鑰就能跑測試與啟動 API。
2. 維運者部署時設定 `APP_ENV=production`；漏設金鑰時，服務啟動即失敗，錯誤訊息一次列出所有缺少的變數名稱。
3. S00 選定或日後更換模型時，只改環境變數，不改程式。

## 需求

- R-001：API 服務提供 `GET /health`，服務可用時回應 200 與 `{"status": "ok"}`。
- R-002：`APP_ENV` 為 `development` 或 `test`（預設 `development`）時，不設定任何 API 金鑰也能載入設定並啟動 API。
- R-003：`APP_ENV` 為 `production` 時，必要設定（`ANTHROPIC_API_KEY`、`HIGGSFIELD_API_KEY`、`HF_IMAGE_MODEL`、`HF_VIDEO_MODEL`）缺少或為空字串即拋出設定錯誤，錯誤訊息一次列出所有缺少的變數名稱。
- R-004：模型名稱（`HF_IMAGE_MODEL`、`HF_VIDEO_MODEL`、`CLAUDE_MODEL`）與成本單價表路徑（`COST_TABLE`）由環境變數或 `.env` 檔決定，環境變數優先。
- R-005：API 金鑰的值不會出現在設定物件的字串表示或設定錯誤訊息中。

## 驗收條件

- AC-001（對應 R-001）：Given API 以測試設定啟動，When 呼叫 `GET /health`，Then 狀態碼為 200，且回應 JSON 的 `status` 為 `"ok"`。
- AC-002（對應 R-002）：Given `APP_ENV=test` 且環境中沒有任何 API 金鑰與模型設定，When 載入設定並建立 API app，Then 不拋出錯誤，且金鑰欄位為空值。
- AC-003（對應 R-003）：Given `APP_ENV=production` 且未設定 `HIGGSFIELD_API_KEY`（其他必要設定齊全），When 載入設定，Then 拋出設定錯誤，訊息包含 `HIGGSFIELD_API_KEY`。
- AC-004（對應 R-003）：Given `APP_ENV=production` 且 `ANTHROPIC_API_KEY`、`HIGGSFIELD_API_KEY`、`HF_VIDEO_MODEL` 皆未設定、`HF_IMAGE_MODEL` 為空字串，When 載入設定，Then 拋出一個設定錯誤，訊息包含全部 4 個名稱。
- AC-005（對應 R-004）：Given 設定檔（`.env`）的 `HF_VIDEO_MODEL` 為 `"vid-model-a"`，When 載入設定，Then 影片模型設定為 `"vid-model-a"`；另 Given 環境變數設定 `HF_IMAGE_MODEL`、`CLAUDE_MODEL`、`COST_TABLE`，且 `.env` 有不同的值，Then 三者皆採用環境變數的值。
- AC-006（對應 R-005）：Given `ANTHROPIC_API_KEY` 設為某個值，When 取得設定物件的 `str()`／`repr()`，或在正式模式因其他欄位缺少而拋出設定錯誤，Then 輸出中不包含該金鑰的值。

## 驗收對應

| AC | 場景 |
|---|---|
| AC-001 | S01-01 |
| AC-002 | S01-01 |
| AC-003 | S01-02 |
| AC-004 | S01-02 |
| AC-005 | S01-03 |
| AC-006 | S01-02 |

AC-002、AC-004、AC-006 除了對應場景之外，細節以單元測試驗證（見 design.md 測試策略）。

## 非功能需求

- `ruff check` 在 `backend/` 無錯誤；`mypy app` 無錯誤。
- pytest 以 `--strict-markers` 執行，註冊 `S00`–`S19`、`integration`、`external` marker；未註冊的 marker 讓收集失敗。
- 測試不讀取開發者本機的 `.env`（避免真實金鑰影響測試結果或進入測試紀錄）。
- 測試與 `scripts/tdd.py` 在沒有網路、沒有金鑰的環境也能執行。

## 假設、風險與待決事項

1. **正式模式的必要設定範圍**：草稿把 `ANTHROPIC_API_KEY`、`HIGGSFIELD_API_KEY` 與兩個 HF 模型名稱列為必要；`FIRECRAWL_API_KEY` 只給種子腳本用（CLAUDE.md），不列入。`CLAUDE_MODEL`、`COST_TABLE` 在 S01 有預設值、不強制。請確認這個範圍。
2. **模型預設值**：開發與測試模式下 `HF_IMAGE_MODEL`／`HF_VIDEO_MODEL` 沒有預設值（為空），避免程式中寫死模型名稱；S00 選定的 `xai/grok-imagine-image-2.0`、`bytedance/seedance-2.5/image-to-video` 只寫在 `.env.example`。`CLAUDE_MODEL` 同理只寫在 `.env.example`（預設空值）。若希望開發模式有預設模型，請說明。
3. **`.env.example` 位置**：開發計畫只寫 `.env.example`，架構書 §12 放在 `infra/`。依文件優先順序以開發計畫為準，草稿放在 repo 根目錄；S05 建立 `infra/` 時不再另放一份。
4. **Higgsfield 金鑰名稱**：S00 spike 使用 `.env.local` 的 `HF_KEY`（格式 `key-id:key-secret`）；本規格依場景 S01-02 改用 `HIGGSFIELD_API_KEY`，值的格式相同。S01 不檢查格式（S12 再處理）。你本機的 `.env.local` 需要自行改名或另外設定。
5. **`.env` 位置**：設定從 repo 根目錄的 `.env` 載入（以 `config.py` 的位置推算，不依賴目前工作目錄）。
6. **閘門使用的 Python**：`tdd.py` 在 `backend/` 執行 `python -m pytest`。Poetry 虛擬環境需要設為 in-project（`backend/.venv`），並在啟用該環境後執行閘門，或設定 `TRS_PYTEST="poetry run python -m pytest"`、`TRS_RUFF="poetry run ruff check ."`。design.md 採用後者並記錄於 README 段落，請確認。
7. 本機 Python 為 3.12.2，符合 3.11+。
