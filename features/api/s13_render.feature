# 架構書 §5.6、構想文件 §5.3
@S13
Feature: 時間軸與影片合成
  所有合成一律以時間軸 JSON 為唯一依據，輸出 15 秒、1080×1920 的 Reels。

  Scenario: S13-01 由鏡頭結果組出時間軸 JSON
    Given 3 個長度分別為 4、5、3 秒的鏡頭結果與 3 秒片尾
    When 組出時間軸 JSON
    Then 影片軌的片段起點依序為 0、4、9、12 秒
    And 總長度為 15 秒
    And 每個片段都有 source 欄位

  Scenario: S13-02 合成 15 秒直式影片
    Given 3 段不同尺寸、24fps 的測試影片與一首 BGM
    When 依時間軸 JSON 合成
    Then 輸出影片為 1080×1920
    And 輸出影片為 30fps
    And 輸出影片長度為 15 ± 0.2 秒
    And 影像編碼為 H.264、音訊編碼為 AAC

  Scenario: S13-03 產生字幕檔
    Given 一份含 3 段字幕的時間軸 JSON
    When 產生 ASS 字幕檔
    Then 字幕檔包含 3 段字幕且時間與時間軸一致
    And 字幕字型為 "Noto Sans TC"

  Scenario: S13-04 BGM 淡入並降低音量
    When 依時間軸 JSON 合成
    Then 輸出影片有音軌
    And 開頭 0.3 秒的平均音量低於中段

  Scenario: S13-05 合成只依據時間軸 JSON
    Given 將時間軸中第 2 段的長度改為 3 秒
    When 依時間軸 JSON 合成
    Then 輸出影片長度為 13 ± 0.2 秒

  Scenario: S13-06 輸出縮圖
    When 依時間軸 JSON 合成
    Then 產生一張 1080×1920 的縮圖
