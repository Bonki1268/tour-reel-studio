import { describe, expect, it } from "vitest";
import { appendTopic, parsePlan, sellingPointLabels } from "./plan";

describe("[S15] sellingPointLabels / appendTopic", () => {
  it("字串與物件賣點都轉成標籤，略過空值", () => {
    expect(sellingPointLabels(["手作早餐", { title: "親子採果", season: [3] }, { name: "x" }, "", 3])).toEqual([
      "手作早餐",
      "親子採果",
    ]);
    expect(sellingPointLabels(null)).toEqual([]);
  });

  it("輸入框為空時直接填入，否則以「、」接上，不重複", () => {
    expect(appendTopic("", "手作早餐")).toBe("手作早餐");
    expect(appendTopic("  ", "手作早餐")).toBe("手作早餐");
    expect(appendTopic("清晨採梅", "手作早餐")).toBe("清晨採梅、手作早餐");
    expect(appendTopic("清晨採梅、手作早餐", "手作早餐")).toBe("清晨採梅、手作早餐");
  });
});

describe("[S15] parsePlan", () => {
  it("讀出企劃與鏡頭欄位", () => {
    const plan = parsePlan({
      title: "梅香晨光",
      concept: "清晨採梅",
      shots: [
        {
          shot_no: 1, role: "hook", duration_s: 4, scene_photo_id: "s1",
          placement: { x: 0.3, y: 0.8, scale: 0.4, flip: false }, action: "揮手", subtitle: "早安！",
        },
      ],
    });
    expect(plan.title).toBe("梅香晨光");
    expect(plan.shots[0]).toEqual({
      shotNo: 1, role: "hook", durationS: 4, scenePhotoId: "s1",
      placement: { x: 0.3, y: 0.8, scale: 0.4, flip: false }, action: "揮手", subtitle: "早安！",
    });
  });

  it("缺欄位時使用預設值", () => {
    const plan = parsePlan({ shots: [{}] });
    expect(plan.title).toBe("—");
    expect(plan.shots[0]).toMatchObject({ shotNo: 1, role: "—", durationS: null, scenePhotoId: null, action: "—", subtitle: "" });
    expect(plan.shots[0].placement).toEqual({ x: 0.5, y: 0.9, scale: 0.5, flip: false });
    expect(parsePlan("bad").shots).toEqual([]);
  });
});
