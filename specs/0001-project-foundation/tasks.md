# 開發骨架與設定載入：任務

> 每個任務小到能完成一次 red–green–refactor；不得有「完成後端」這類無法驗收的任務。

| 任務 | 前置 | 對應 R／AC | 修改範圍 | 先寫的測試 | 完成證據 |
|---|---|---|---|---|---|
| T-01 | — | （非功能需求） | `backend/pyproject.toml`、`backend/poetry.toml`、目錄骨架、`.gitignore`、`backend/tests/conftest.py` | `poetry run python -m pytest --collect-only` 可收集；未註冊 marker 讓收集失敗 | `poetry install` 成功、`ruff check .` 無錯誤 |
| T-02 | T-01 | R-002／AC-002 | `backend/app/config.py` | `test_r002_test_mode_loads_without_keys`、`test_r002_default_env_is_development` | 測試通過 |
| T-03 | T-02 | R-003／AC-003、AC-004 | `backend/app/config.py` | `test_r003_production_lists_all_missing_names`、`test_r003_production_treats_blank_as_missing`、`test_r003_production_ok_when_all_required_set`、場景 S01-02 | 測試通過 |
| T-04 | T-02 | R-004／AC-005 | `backend/app/config.py` | `test_r004_env_var_overrides_env_file`、場景 S01-03 | 測試通過 |
| T-05 | T-03 | R-005／AC-006 | `backend/app/config.py` | `test_r005_secret_not_in_repr_or_error` | 測試通過 |
| T-06 | T-02 | R-001、R-002／AC-001、AC-002 | `backend/app/api/main.py` | `test_r001_health_returns_ok`、場景 S01-01 | 測試通過 |
| T-07 | T-03、T-04 | R-003、R-004 | `.env.example` | —（文件） | 列出 §9.2 所有設定名稱與說明，不含真實金鑰；閘門金鑰掃描通過 |
| T-08 | T-01～T-07 | 全部 | — | `python3 scripts/tdd.py gate` | 閘門通過、`mypy app` 無錯誤 |

## 需求追蹤矩陣

| 需求 | 驗收條件 | BDD 場景 | TDD／整合測試 | 實作位置 | 狀態 |
|---|---|---|---|---|---|
| R-001 | AC-001 | `S01-01` | `test_r001_health_returns_ok` | `backend/app/api/main.py` | 完成 |
| R-002 | AC-002 | `S01-01` | `test_r002_test_mode_loads_without_keys`、`test_r002_default_env_is_development` | `backend/app/config.py` | 完成 |
| R-003 | AC-003、AC-004 | `S01-02` | `test_r003_production_lists_all_missing_names`、`test_r003_production_treats_blank_as_missing`、`test_r003_production_ok_when_all_required_set` | `backend/app/config.py` | 完成 |
| R-004 | AC-005 | `S01-03` | `test_r004_env_var_overrides_env_file` | `backend/app/config.py` | 完成 |
| R-005 | AC-006 | `S01-02` | `test_r005_secret_not_in_repr_or_error` | `backend/app/config.py` | 完成 |
