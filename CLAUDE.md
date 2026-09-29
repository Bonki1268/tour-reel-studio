# Tour Reel Studio — Claude Code 開發規則

觀光業者用的 AI 宣傳短片系統：業者選主題、確認企劃與成本，系統以已定妝角色與實景照產出 15 秒 IG Reels。

## 開發方法：規格驅動（SDD）＋ BDD／TDD 驗證

**沒有已核准的 spec package，就沒有產品程式碼。** 完整規範見 `docx/spec-driven-development.md`。

每個步驟的順序：**規格草稿 → 使用者核准 → 紅燈 → 綠燈 → 重構 → 閘門（自動 commit 並 push）**。
用 `/next-step` 依序完成目前步驟。

### 文件優先順序（衝突時）

1. 已核准的 `specs/<package>/spec.md`
2. 同一 package 的 `design.md` 契約與 `features/` 中對應的 BDD 場景
3. `docx/development-plan.md`
4. `docx/system-architecture.md`
5. `docx/tourism-ai-video-concept.md`

文件矛盾、規格缺少驗收條件，或需求有多種合理解讀時：**停止實作，向使用者說明衝突並等待決定**，不得自行選擇產品行為。

### 目前的實作狀態

`spec-driven-development.md` §10 的 bootstrap 中，以下項目已建立：`features/`（S01–S19 共 101 個場景）、`scripts/tdd.py`、`.tdd/progress.json`、`.claude/hooks/`、`specs/` 範本與 `changes/`。尚未建立的是各步驟的 spec package、產品程式碼與 CI。

## 閘門指令

```bash
python3 scripts/tdd.py status   # 目前步驟與下一個動作
python3 scripts/tdd.py show     # 步驟說明、規格狀態、場景清單
python3 scripts/tdd.py spec     # 規格結構自檢（草稿也可以）
python3 scripts/tdd.py red      # 規格已核准＋測試齊全＋確實失敗 → 記錄紅燈並在本機 commit
python3 scripts/tdd.py gate     # lint＋回歸＋場景覆蓋 → 寫 evidence → commit 並 push
```

- 一次只做一個步驟（S00 → S19）；閘門會重跑所有已完成步驟的測試。
- `red` 要求：規格狀態為 approved 且有核准者、每個 AC 對應到場景、每個場景都被 AC 對應、所有場景都有測試、單元測試數達標、測試確實失敗（不是匯入錯誤）。
- `gate` 要求：lint 通過、S01 到目前步驟的測試全數通過且沒有 skip／xfail、每個場景都有通過的測試、報告已填寫。

### Commit 與 push

- 由 `tdd.py` 自動處理：`red` 在本機 commit `test(SNN): 紅燈 — …`；`gate` 通過後 commit `feat(SNN): …` 並 push。
- commit 前會掃描 `.env`、金鑰檔與疑似 API 金鑰；發現時取消 commit 並警告。
- **不要自己執行 git commit、git push**，也不可 force push 或使用 `--no-verify`。push 失敗時照實回報給使用者。

## 絕對禁止

- 修改 `features/`、`scripts/tdd.py`、`.tdd/`、`.claude/`、`docx/development-plan.md`、`docx/spec-driven-development.md`、`specs/_template/`、`specs/*/evidence.md`，或已核准的 `spec.md`（hook 會阻擋並記錄）
- 寫入或更改任何核准欄位：「狀態」「核准者／時間」「審核人」「驗收者」
- 在規格核准前寫測試或產品程式碼
- 刪除、略過、xfail 或弱化測試來通過閘門；在測試中寫死結果配合實作
- 在 `docx/validation/` 報告填入未實際執行的結果
- 未經使用者明確同意就呼叫真實外部 API、產生費用、部署，或執行 `tdd.py unlock`／`lock`

規格或場景需要修改時：起草 `changes/CR-xxxx.md`（範本 `changes/_template.md`），說明動機與影響，等使用者核准並解除保護。

## 測試慣例

### 後端（pytest＋pytest-bdd）

- 每個測試都要有步驟標記：模組層級 `pytestmark = pytest.mark.S05`；閘門拒絕沒有標記的測試。
- 單元測試名稱帶需求編號：`test_r002_hash_ignores_key_order`。
- Gherkin 標籤自動成為 marker（`@S05`、`@integration`、`@external`）。場景綁定：`scenarios("api/s05_persistence.feature")`，`bdd_features_base_dir` 指向 repo 根目錄的 `features/`。
- 場景標題以編號開頭（`S05-03 …`），閘門以此比對規格的「驗收對應」與測試結果。
- `@integration` 需要 PostgreSQL／Redis／MinIO，由 `infra/docker-compose.test.yml` 提供，閘門自動啟動。
- `@external` 呼叫真實 API，不列入閘門；只在使用者同意並提供金鑰時執行。
- 外部服務以假實作或 HTTP mock 測試（`FakeProvider`、`FakeCreativeEngine`、`FakeRenderer`、記憶體儲存、`respx`），但供應商契約本身仍需 `@external` 或整合測試驗證。

### 前端（vitest＋playwright-bdd）

- 單元測試 `describe` 名稱以步驟開頭：`describe("[S15] placement", …)`。
- 驗收測試用 playwright-bdd，從 `features/web/*.feature` 產生；步驟定義放在 `apps/web/e2e/steps/`。
- S15、S16 以 Playwright route mock 攔截 API；S19 連接真實後端（FakeProvider）。
- 可用已安裝的 `playwright-cli` skill 除錯頁面。

## 技術選型（架構書 §4）

- 後端：Python 3.11+、FastAPI、Pydantic、SQLAlchemy、Alembic、arq、FFmpeg、Pillow；套件管理 Poetry；ruff、mypy
- 前端：Next.js、TypeScript、react-konva
- 資料：PostgreSQL、Redis、S3 相容儲存（開發與測試用 MinIO）
- 外部：Claude API（企劃）、Higgsfield API（關鍵幀、圖生影片）、Firecrawl（僅種子腳本）

## 程式碼風格

- 簡潔、有效率；領域邏輯放 `backend/app/domain/`，不依賴外部服務
- 外部服務一律經由介面（`CreativeEngine`、`ImageProvider`、`VideoProvider`、`Storage`），模型名稱只從設定讀取
- 註解與使用者可見文字用繁體中文；程式識別名稱用英文
- API 金鑰只存在環境變數（`.env` 已列入 `.gitignore`），不寫進程式碼、測試、fixture 或日誌

## 每次回覆要包含

完成任何變更後，列出：對應的 R／AC、執行的測試指令與結果、commit 編號與 push 狀態、仍未解決的問題。
