# 架構書 §1.2、§9.4；構想文件 §8.1（Demo 成功定義）
@S19 @fullstack
Feature: 端對端驗收
  前後端實際連線、以 FakeProvider 跑完整快速流程；真實生成另以報告驗收。

  Background:
    Given 以測試 docker compose 啟動全系統，Provider 為 FakeProvider
    And 已執行種子腳本

  Scenario: S19-01 完成完整快速流程
    When 使用者從選題操作到下載成品
    Then 下載的 MP4 為 1080×1920
    And 下載的 MP4 長度為 15 ± 0.2 秒

  Scenario: S19-02 使用者只需要兩次確認
    When 使用者從選題操作到下載成品
    Then 使用者只進行了「核准企劃」與「確認成品」兩次確認

  Scenario: S19-03 單鏡失敗後在成品確認前完成重生
    Given FakeProvider 對第 2 鏡第 1 次與第 2 次都失敗、第 3 次成功
    When 使用者核准企劃後，在第 2 鏡失敗時選擇重生
    Then 最後仍能下載完整的 15 秒成品

  @external
  Scenario: S19-04 真實生成在 10 分鐘內完成
    Given Provider 為真實的 Higgsfield
    When 使用者從選題操作到下載成品
    Then 全程不超過 10 分鐘
