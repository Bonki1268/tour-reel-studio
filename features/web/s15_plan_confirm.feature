# 架構書 §5.2（確認點 1）、§5.3
@S15
Feature: 選題與企劃確認
  以 Playwright 攔截 API 請求（route mock），驗證前端的選題、企劃確認與角色擺放。

  Background:
    Given 已開啟 Demo 專案頁面，API 以 mock 回應

  Scenario: S15-01 輸入主題並送出
    When 輸入主題 "清晨採梅體驗" 並送出
    Then 畫面顯示企劃產生中
    And 收到 "plan_ready" 事件後顯示 2 到 3 張企劃卡

  Scenario: S15-02 點選品牌賣點快速填入主題
    When 點選品牌賣點 "手作早餐"
    Then 主題輸入框的內容包含 "手作早餐"

  Scenario: S15-03 企劃卡顯示鏡頭摘要與成本
    Given 企劃已產生
    Then 每張企劃卡顯示 3 鏡的摘要
    And 顯示預估點數與成本上限

  Scenario: S15-04 拖曳角色調整擺放
    Given 已選擇第 1 個企劃
    When 在第 1 鏡的實景照上把角色拖到右下方
    Then 送出的第 1 鏡擺放參數 x 大於 0.5
    And 送出的第 1 鏡擺放參數 y 大於 0.5

  Scenario: S15-05 未同意成本上限時不能核准
    Given 已選擇第 1 個企劃
    And 尚未勾選同意成本上限
    Then 核准按鈕為停用狀態

  Scenario: S15-06 核准後進入生成頁面
    Given 已選擇第 1 個企劃並勾選同意成本上限
    When 按下核准
    Then approve-plan 請求帶有 Idempotency-Key 標頭
    And 請求內容包含 plan_id、每鏡的擺放參數與 cost_cap
    And 畫面進入生成進度頁
