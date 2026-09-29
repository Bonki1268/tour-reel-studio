# 架構書 §9.3
@S18
Feature: Demo 可靠性
  現場網路不可控：沒有 webhook 也要能完成，重複通知只處理一次，Worker 重啟能接續。

  Scenario: S18-01 關閉 webhook 時以輪詢完成
    Given WEBHOOK_ENABLED 為 false
    When 執行一個影片生成工作
    Then 工作透過輪詢完成並轉存

  Scenario: S18-02 webhook 遺失時輪詢補上
    Given WEBHOOK_ENABLED 為 true 但 webhook 始終未送達
    When 執行一個影片生成工作
    Then 工作透過輪詢完成並轉存

  Scenario: S18-03 webhook 與輪詢同時回報只處理一次
    Given 同一個工作的 webhook 與輪詢結果同時到達
    When 兩者都被處理
    Then 結果只轉存一次
    And 成本帳只記一筆

  Scenario: S18-04 Worker 重啟後接續進行中的工作
    Given 有一個狀態為 "submitted" 的工作
    When Worker 重新啟動
    Then 該工作恢復輪詢並完成

  Scenario: S18-05 生成超時時提供保底成品
    Given 已設定保底成品 DEMO_FALLBACK_VIDEO
    And 生成時間超過設定的展示門檻
    When 前端查詢影片狀態
    Then 回應包含保底成品網址
    And 背景生成仍繼續進行
