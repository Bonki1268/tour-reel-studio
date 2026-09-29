# 開發骨架與設定載入：設計

> 對應規格：spec.md（版本 v1）。本檔由 Claude Code 撰寫，隨規格核准一併審閱。

## 設計概要

```
tour-reel-studio/
├─ .env.example                 所有設定名稱與說明；不含真實值
├─ .gitignore                   新增 .env、.env.*、!.env.example、backend/.venv
└─ backend/
   ├─ pyproject.toml            Poetry；pytest、ruff、mypy 設定
   ├─ poetry.toml               virtualenvs.in-project = true
   ├─ app/
   │  ├─ config.py              Settings、ConfigError、load_settings()
   │  ├─ api/main.py            create_app(settings) 與模組層級 app
   │  └─ domain/ creative/ providers/ render/ jobs/ storage/ seed/   （只有 __init__.py）
   └─ tests/
      ├─ conftest.py            清除設定相關環境變數、禁止讀取真實 .env
      ├─ unit/test_config.py
      └─ bdd/test_s01_skeleton.py   scenarios("api/s01_skeleton.feature")
```

依賴：fastapi、pydantic-settings、uvicorn（執行用）；開發依賴：pytest、pytest-bdd、pytest-asyncio、httpx、ruff、mypy。

### 設定（`app/config.py`）

```python
AppEnv = Literal["development", "test", "production"]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    app_env: AppEnv = "development"
    anthropic_api_key: SecretStr | None = None
    higgsfield_api_key: SecretStr | None = None
    firecrawl_api_key: SecretStr | None = None
    hf_image_model: str = ""
    hf_video_model: str = ""
    claude_model: str = ""
    cost_table: Path = REPO_ROOT / "config" / "cost_table.json"   # 檔案內容由 S04 定義
    retry_reserve_ratio: float | None = None                      # 架構書 §9.2；S04 決定語意
    webhook_enabled: bool = True

class ConfigError(Exception):
    missing: tuple[str, ...]      # 缺少的環境變數名稱（大寫）

def load_settings(env_file: Path | None = ..., **overrides) -> Settings
```

- `load_settings()` 建立 `Settings`，在 `app_env == "production"` 時檢查 `REQUIRED_IN_PRODUCTION`，把缺少或空白的欄位**一次收集**後拋出 `ConfigError`，訊息例如：
  `正式環境缺少必要設定：ANTHROPIC_API_KEY, HIGGSFIELD_API_KEY, HF_IMAGE_MODEL`
- 必要檢查放在 `load_settings()` 而不是 Pydantic validator：Pydantic 的 `ValidationError` 會附上輸入值，可能把其他欄位的金鑰帶進訊息（R-005）。
- 金鑰欄位用 `SecretStr`，`repr()` 只顯示 `**********`。
- `env_file` 參數讓測試指定暫存的 `.env`（場景 S01-03），或傳 `None` 完全不讀檔。

### API（`app/api/main.py`）

- `create_app(settings: Settings | None = None) -> FastAPI`：未傳入時呼叫 `load_settings()`，把設定放在 `app.state.settings`。
- 以 factory 啟動：`uvicorn app.api.main:create_app --factory`；正式模式缺金鑰時 `create_app()` 拋出 `ConfigError`，即「拒絕啟動」。
- 不提供模組層級的 `app = create_app()`（實作時修訂）：模組層級建立會在 pytest 收集階段就讀取開發者的 shell 環境與 `.env`，早於 `conftest.py` 的隔離 fixture，違反「測試不讀取本機 `.env`」。

## 資料模型／狀態轉換變更

無。

## API 契約（request／response、錯誤碼）

| 方法 | 路徑 | 回應 |
|---|---|---|
| GET | `/health` | 200 `{"status": "ok"}` |

S01 的 `/health` 只表示程序存活；依賴服務的檢查在 S05 之後擴充，並另開 CR 或在該步驟規格定義。

## 失敗行為、安全與可觀測性

- 正式模式缺少設定：啟動失敗，`ConfigError` 只列變數名稱，不含任何值。
- `.env`、`.env.*` 列入 `.gitignore`；`.env.example` 只放名稱、說明與 S00 選定的模型名稱。
- 測試的 `conftest.py` 以 autouse fixture 刪除所有設定相關的環境變數，並讓 `load_settings` 預設不讀取 repo 的 `.env`，避免開發者的真實金鑰被讀進測試。

## 測試策略

| 需求 | 驗收條件 | 測試層級 | 測試位置 |
|---|---|---|---|
| R-001 | AC-001 | BDD（S01-01）＋Unit | `backend/tests/bdd/test_s01_skeleton.py`、`backend/tests/unit/test_health.py` |
| R-002 | AC-002 | BDD（S01-01）＋Unit | `backend/tests/unit/test_config.py::test_r002_*` |
| R-003 | AC-003、AC-004 | BDD（S01-02）＋Unit | `backend/tests/unit/test_config.py::test_r003_*` |
| R-004 | AC-005 | BDD（S01-03）＋Unit | `backend/tests/unit/test_config.py::test_r004_*` |
| R-005 | AC-006 | Unit | `backend/tests/unit/test_config.py::test_r005_*` |

- BDD 使用 `fastapi.testclient.TestClient`（httpx），不啟動真實伺服器。
- S01-03 的「設定檔」以 `tmp_path` 寫入暫存 `.env`，傳給 `load_settings(env_file=...)`。
- 每個測試模組 `pytestmark = pytest.mark.S01`；BDD 模組另外由 feature 的 `@S01` 標籤帶入。
- 預計單元測試（≥ 2，預計 8）：
  - `test_r001_health_returns_ok`
  - `test_r002_test_mode_loads_without_keys`
  - `test_r002_default_env_is_development`
  - `test_r003_production_lists_all_missing_names`
  - `test_r003_production_treats_blank_as_missing`
  - `test_r003_production_ok_when_all_required_set`
  - `test_r004_env_var_overrides_env_file`（模型名稱與 `COST_TABLE`）
  - `test_r005_secret_not_in_repr_or_error`
- 閘門執行方式：`TRS_PYTEST="poetry run python -m pytest"`、`TRS_RUFF="poetry run ruff check ."`（`tdd.py` 在 `backend/` 執行）。

## ADR（影響公開 API、資料遷移、成本、外部供應商或安全性時必填）

- 決定：必要設定檢查在 `load_settings()` 中手動收集，不用 Pydantic 的 required 欄位或 validator；模型名稱在程式中沒有預設值。
- 替代方案：(a) 以 Pydantic 必填欄位＋`model_validator` 檢查；(b) 開發模式預設使用 S00 選定的模型名稱。
- 取捨：(a) 的 `ValidationError` 會附帶輸入值，有洩漏金鑰的風險，且開發／正式模式的必填差異不好表達；手動檢查多幾行程式但訊息可控。(b) 較方便，但等於把模型名稱寫進程式，違反「模型名稱只從設定讀取」；改由 `.env.example` 提供建議值。
