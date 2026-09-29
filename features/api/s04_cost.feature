# 架構書 §6.4
@S04
Feature: 成本估算與預算控制
  生成前顯示預估成本；任何工作送出前都要檢查不會超過使用者核准的上限。

  Background:
    Given 單價表為
      | kind     | model       | credits |
      | keyframe | img-model-a | 5       |
      | video    | vid-model-a | 30      |
    And 成本上限預留 1 鏡的完整重生費用

  Scenario: S04-01 估算 3 鏡影片的成本與上限
    When 估算一支 3 鏡影片的成本
    Then 預估成本為 105 點
    And 成本上限為 140 點

  Scenario: S04-02 預算內允許送出
    Given 成本上限為 140 點，已花費 70 點
    When 準備送出一個預估 30 點的影片工作
    Then 允許送出

  Scenario: S04-03 超出預算時暫停並要求重新確認
    Given 成本上限為 140 點，已花費 120 點
    When 準備送出一個預估 30 點的影片工作
    Then 拒絕送出並回報「超出預算上限」
    And 影片需要使用者重新確認成本

  Scenario: S04-04 以供應商回報的實際成本記帳
    Given 一個預估 30 點的影片工作
    When 供應商回報實際成本 28 點
    Then 成本帳新增一筆 28 點
    And 已花費金額增加 28 點

  Scenario: S04-05 供應商未回報成本時以單價表記帳
    Given 一個使用 "vid-model-a" 的影片工作
    When 工作完成但供應商沒有回報成本
    Then 成本帳新增一筆 30 點

  Scenario: S04-06 單價表缺少模型時拒絕估算
    When 估算使用 "unknown-model" 的工作成本
    Then 應拋出單價表錯誤並指出缺少 "unknown-model"
