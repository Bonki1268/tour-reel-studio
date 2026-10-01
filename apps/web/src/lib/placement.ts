// 角色擺放：照片座標比例值（0–1）與畫面像素互換（架構書 §5.3；spec 0015 R-004）

export type Placement = { x: number; y: number; scale: number; flip: boolean };
export type Display = { width: number; height: number };
export type Point = { px: number; py: number };

export const SCALE_MIN = 0.1;
export const SCALE_MAX = 0.9;
const DEFAULT: Placement = { x: 0.5, y: 0.9, scale: 0.5, flip: false };

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const round6 = (v: number) => Math.round(v * 1e6) / 1e6;
const num = (v: unknown, fallback: number) => (typeof v === "number" && Number.isFinite(v) ? v : fallback);

/** 照片以 maxWidth 為上限等比顯示（不放大）。 */
export function displaySize(photo: { width: number; height: number }, maxWidth: number): Display {
  const width = Math.min(photo.width, maxWidth);
  return { width, height: Math.round((width * photo.height) / photo.width) };
}

export function toRatio(point: Point, display: Display): { x: number; y: number } {
  return {
    x: round6(clamp(point.px / display.width, 0, 1)),
    y: round6(clamp(point.py / display.height, 0, 1)),
  };
}

export function toPixels(ratio: { x: number; y: number }, display: Display): Point {
  return { px: round6(ratio.x * display.width), py: round6(ratio.y * display.height) };
}

/** 補上預設值並夾在範圍內：x、y ∈ [0, 1]，scale ∈ [0.1, 0.9]。 */
export function clampPlacement(p: Partial<Placement> | null | undefined): Placement {
  return {
    x: clamp(num(p?.x, DEFAULT.x), 0, 1),
    y: clamp(num(p?.y, DEFAULT.y), 0, 1),
    scale: clamp(num(p?.scale, DEFAULT.scale), SCALE_MIN, SCALE_MAX),
    flip: p?.flip === true,
  };
}

/** 角色在畫面中的框：腳底中心在 (x, y)，高度為 scale × 照片高度，寬度依去背圖長寬比。 */
export function characterBox(
  p: Placement,
  display: Display,
  aspect: number,
): { left: number; top: number; width: number; height: number } {
  const height = round6(p.scale * display.height);
  const width = round6(height * aspect);
  const { px, py } = toPixels(p, display);
  return { left: round6(px - width / 2), top: round6(py - height), width, height };
}
