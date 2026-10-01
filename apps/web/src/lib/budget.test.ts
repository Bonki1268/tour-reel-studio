import { describe, expect, it } from "vitest";
import { needsConfirmation, newCap, remaining } from "./budget";

describe("[S16] budget", () => {
  it("剩餘預算 = 上限 − 已花費", () => {
    expect(remaining("140", "120")).toBe(20);
    expect(remaining("40.5", "10.25")).toBeCloseTo(30.25);
    expect(remaining(null, "10")).toBeNull();
  });

  it("所需點數超過剩餘預算時需要再次確認", () => {
    expect(needsConfirmation("35", 20)).toBe(true);
    expect(needsConfirmation("20", 20)).toBe(false);
    expect(needsConfirmation("5.5", 20)).toBe(false);
    expect(needsConfirmation("35", null)).toBe(true);
  });

  it("新上限 = 已花費 + 所需點數", () => {
    expect(newCap("120", "35")).toBe("155");
    expect(newCap("10.25", "1.5")).toBe("11.75");
    expect(newCap("0.1", "0.2")).toBe("0.3");
  });
});
