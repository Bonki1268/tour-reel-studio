# 架構書 §5.5、§4.5（構想文件）
@S12
Feature: Higgsfield adapter
  以 HTTP mock 驗證 adapter 的行為；實作前先閱讀 https://docs.higgsfield.ai/docs 確認實際端點與欄位。

  Background:
    Given 以 HTTP mock 模擬 Higgsfield API

  Scenario: S12-01 送出圖生影片請求
    When 以關鍵幀與提示詞送出圖生影片請求
    Then 請求使用設定檔的 HF_VIDEO_MODEL
    And 請求帶入關鍵幀網址與提示詞
    And 請求關閉音訊生成
    And 回傳包含 external_id 的 ProviderJob

  Scenario: S12-02 送出精修合成請求
    When 以粗合成圖、遮罩與身份板送出合成請求
    Then 請求使用設定檔的 HF_IMAGE_MODEL
    And 回傳包含 external_id 的 ProviderJob

  Scenario: S12-03 輪詢直到完成
    Given 查詢狀態依序回傳 "queued", "in_progress", "completed"
    When 輪詢該工作
    Then 取得結果網址

  Scenario: S12-04 結果立即轉存
    Given 一個已完成的工作
    When 取得結果
    Then 檔案下載至自有物件儲存
    And 生成工作只記錄自有儲存路徑

  Scenario: S12-05 webhook 簽章錯誤時拒絕
    When 以錯誤的簽章呼叫 POST /webhooks/higgsfield
    Then 回應狀態碼為 401
    And 不更新任何生成工作

  Scenario Outline: S12-06 API 錯誤分類
    Given Higgsfield 回應 HTTP <status>
    When 送出圖生影片請求
    Then 錯誤被歸類為 "<kind>"

    Examples:
      | status | kind          |
      | 429    | retryable     |
      | 503    | retryable     |
      | 400    | non_retryable |
      | 401    | non_retryable |

  Scenario: S12-07 API 金鑰不出現在日誌
    When 送出圖生影片請求並記錄日誌
    Then 日誌中找不到 API 金鑰

  @external
  Scenario: S12-08 真實 API 冒煙測試
    Given 已設定真實的 HIGGSFIELD_API_KEY
    When 以測試關鍵幀送出一次圖生影片請求
    Then 在 10 分鐘內取得可播放的影片
