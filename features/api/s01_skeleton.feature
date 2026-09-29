# 架構書 §4、§9.2、§12
@S01
Feature: 開發骨架與測試閘門
  作為開發者，我需要可執行的後端骨架與設定載入，之後每一步都能在同一套測試基礎上累積。

  Scenario: S01-01 健康檢查
    Given API 服務以測試設定啟動
    When 呼叫 GET /health
    Then 回應狀態碼為 200
    And 回應內容的 status 為 "ok"

  Scenario: S01-02 正式模式缺少必要金鑰時拒絕啟動
    Given 環境變數 APP_ENV 為 "production"
    And 未設定 HIGGSFIELD_API_KEY
    When 載入系統設定
    Then 應拋出設定錯誤並指出缺少 "HIGGSFIELD_API_KEY"

  Scenario: S01-03 模型名稱由設定檔決定
    Given 設定檔的 HF_VIDEO_MODEL 為 "vid-model-a"
    When 載入系統設定
    Then 影片模型設定為 "vid-model-a"
