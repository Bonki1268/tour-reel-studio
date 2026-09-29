# 架構書 §5.2
@S07
Feature: 快速模式工作編排
  以假的創作引擎、供應商與儲存，驗證從主題到成品的完整編排邏輯。

  Background:
    Given 一個含品牌檔案、1 個已鎖定角色與 3 張實景照的專案
    And 使用 FakeCreativeEngine、FakeProvider、FakeRenderer 與記憶體儲存

  Scenario: S07-01 從主題到成品的完整快速流程
    When 使用者送出主題 "清晨採梅體驗"
    Then 影片狀態變為 "plan_ready" 並有 2 到 3 個企劃
    When 使用者選擇第 1 個企劃並以預估上限核准
    Then 3 個鏡頭各自產生關鍵幀與影片
    And 影片狀態依序經過 "generating", "rendering", "review"
    And 產生一份時間軸 JSON 與一個成品檔

  Scenario: S07-02 3 鏡平行生成
    Given FakeProvider 每個工作耗時 1 秒
    When 核准企劃後開始生成
    Then 所有鏡頭在 3 秒內完成生成

  Scenario: S07-03 每個階段發布進度事件
    When 完成一次完整快速流程
    Then 進度事件依序包含 "plan_ready", "shot_started", "shot_done", "render_started", "review_ready"
    And 每個事件都帶有 video_id

  Scenario: S07-04 單鏡失敗不影響其他鏡頭
    Given FakeProvider 對第 2 鏡永遠失敗
    When 核准企劃後開始生成
    Then 第 1 鏡與第 3 鏡完成
    And 影片狀態變為 "needs_attention"

  Scenario: S07-05 成品確認時重生單鏡
    Given 一支狀態為 "review" 的影片
    When 使用者重生第 3 鏡
    Then 只有第 3 鏡產生新版本
    And 成品重新合成
    And 影片回到 "review"

  Scenario: S07-06 流程中只有兩個需要使用者確認的節點
    When 完成一次完整快速流程
    Then 使用者核准紀錄只有 "plan" 與 "final" 兩筆
    And 其餘核准紀錄的 auto_approved 皆為 true
