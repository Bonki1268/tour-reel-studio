import { describe, expect, it } from "vitest";
import { formatCredits } from "./format";

describe("[S15] formatCredits", () => {
  it.each([
    ["1234.5", "1,234.5 點"],
    ["12", "12 點"],
    ["0.125", "0.13 點"],
    [1234567, "1,234,567 點"],
    ["40.00", "40 點"],
  ])("%s → %s", (input, expected) => {
    expect(formatCredits(input)).toBe(expected);
  });

  it("無法解析時顯示破折號", () => {
    expect(formatCredits("abc")).toBe("— 點");
  });
});
