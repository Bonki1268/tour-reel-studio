import { describe, expect, it } from "vitest";
import { characterBox, clampPlacement, displaySize, toPixels, toRatio } from "./placement";

describe("[S15] placement", () => {
  it("照片依最大寬度等比縮放顯示", () => {
    expect(displaySize({ width: 1080, height: 1920 }, 270)).toEqual({ width: 270, height: 480 });
    expect(displaySize({ width: 540, height: 960 }, 1000)).toEqual({ width: 540, height: 960 });
  });

  it("縮放顯示時像素與比例值互換一致", () => {
    const display = displaySize({ width: 1080, height: 1920 }, 270);
    for (const ratio of [{ x: 0, y: 0 }, { x: 0.5, y: 0.9 }, { x: 0.123, y: 0.987 }, { x: 1, y: 1 }]) {
      const back = toRatio(toPixels(ratio, display), display);
      expect(back.x).toBeCloseTo(ratio.x, 3);
      expect(back.y).toBeCloseTo(ratio.y, 3);
    }
    expect(toPixels({ x: 0.5, y: 0.9 }, display)).toEqual({ px: 135, py: 432 });
  });

  it("超出照片的座標夾在 0–1", () => {
    const display = { width: 270, height: 480 };
    expect(toRatio({ px: -20, py: 600 }, display)).toEqual({ x: 0, y: 1 });
    expect(toRatio({ px: 300, py: -1 }, display)).toEqual({ x: 1, y: 0 });
  });

  it("擺放參數補上預設值並夾在範圍內", () => {
    expect(clampPlacement({ x: 1.4, y: -0.2, scale: 1, flip: true })).toEqual({ x: 1, y: 0, scale: 0.9, flip: true });
    expect(clampPlacement({ x: 0.3, y: 0.8, scale: 0.01 })).toEqual({ x: 0.3, y: 0.8, scale: 0.1, flip: false });
    expect(clampPlacement(null)).toEqual({ x: 0.5, y: 0.9, scale: 0.5, flip: false });
  });

  it("角色框以腳底中心定位、高度依 scale、寬度依長寬比", () => {
    const box = characterBox({ x: 0.5, y: 0.9, scale: 0.5, flip: false }, { width: 270, height: 480 }, 0.5);
    expect(box).toEqual({ left: 75, top: 192, width: 120, height: 240 });
  });
});
