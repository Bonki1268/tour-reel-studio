# 架構書 §6.1
@S02
Feature: 影片狀態機
  影片的狀態只能依規定的事件轉換，任何不合法的轉換都必須被拒絕。

  Scenario Outline: S02-01 合法的狀態轉換
    Given 一支狀態為 "<from>" 的影片
    When 發生事件 "<event>"
    Then 影片狀態變為 "<to>"

    Examples:
      | from            | event              | to              |
      | draft           | submit_topic       | planning        |
      | planning        | plans_ready        | plan_ready      |
      | planning        | planning_failed    | failed          |
      | plan_ready      | regenerate_plans   | planning        |
      | plan_ready      | approve_plan       | generating      |
      | generating      | all_shots_done     | rendering       |
      | generating      | shot_failed_final  | needs_attention |
      | needs_attention | confirm_regenerate | generating      |
      | rendering       | render_done        | review          |
      | review          | regenerate_shot    | generating      |
      | review          | approve_final      | approved        |

  Scenario: S02-02 不合法的狀態轉換被拒絕
    Given 一支狀態為 "generating" 的影片
    When 發生事件 "approve_plan"
    Then 應拋出狀態轉換錯誤
    And 影片狀態仍為 "generating"

  Scenario: S02-03 已完成的影片不能再變更
    Given 一支狀態為 "approved" 的影片
    When 發生事件 "regenerate_shot"
    Then 應拋出狀態轉換錯誤

  Scenario: S02-04 狀態轉換留下紀錄
    Given 一支狀態為 "draft" 的影片
    When 依序發生事件 "submit_topic" 與 "plans_ready"
    Then 影片的狀態歷程依序為 "draft", "planning", "plan_ready"
