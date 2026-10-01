import { describe, expect, it } from "vitest";
import { createBackoff } from "./backoff";

describe("[S16] backoff", () => {
  it("1、2、4、8 秒後固定 15 秒", () => {
    const b = createBackoff();
    expect(Array.from({ length: 7 }, () => b.next())).toEqual([1, 2, 4, 8, 15, 15, 15]);
  });

  it("連線成功後歸零", () => {
    const b = createBackoff();
    b.next();
    b.next();
    b.reset();
    expect(b.next()).toBe(1);
  });
});
