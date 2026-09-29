# 架構書 §5.2（確認點 2）
@S16
Feature: 生成進度與成品確認
  以 Playwright 攔截 API 與 SSE，驗證進度顯示、單鏡重生與成品下載。

  Background:
    Given 已開啟一支生成中影片的進度頁，API 以 mock 回應

  Scenario: S16-01 顯示每鏡進度
    When 依序收到第 1、2、3 鏡的 "shot_done" 事件
    Then 3 鏡都顯示為完成

  Scenario: S16-02 單鏡失敗時顯示重生選項
    When 收到影片狀態為 "needs_attention"、第 2 鏡失敗的事件
    Then 第 2 鏡顯示失敗與重生按鈕
    And 重生按鈕旁顯示所需點數

  Scenario: S16-03 成品播放與下載
    When 收到 "review_ready" 事件
    Then 畫面顯示可播放的成品
    And 按下下載會開啟預簽名下載網址

  Scenario: S16-04 重生超出剩餘預算時要求再次確認
    Given 影片狀態為 "review"，剩餘預算 20 點
    When 對第 3 鏡按下重生，所需 35 點
    Then 顯示超出預算的確認對話框
    And 未確認前不送出重生請求

  Scenario: S16-05 SSE 斷線後自動重連並補回狀態
    When SSE 連線中斷
    Then 前端重新連線
    And 重新取得 GET /videos/{id} 的最新狀態

  Scenario: S16-06 成品確認
    Given 影片狀態為 "review"
    When 按下「確認成品」
    Then 送出 POST /videos/{id}/approve
    And 畫面顯示已完成
