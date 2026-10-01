// 角色擺放：照片座標比例值（0–1）與畫面像素互換（架構書 §5.3；spec 0015 R-004）

export type Placement = { x: number; y: number; scale: number; flip: boolean };
export type Display = { width: number; height: number };
export type Point = { px: number; py: number };

export const SCALE_MIN = 0.1;
export const SCALE_MAX = 0.9;

export function displaySize(photo: { width: number; height: number }, maxWidth: number): Display {
  throw new Error("not implemented");
}

export function toRatio(point: Point, display: Display): { x: number; y: number } {
  throw new Error("not implemented");
}

export function toPixels(ratio: { x: number; y: number }, display: Display): Point {
  throw new Error("not implemented");
}

export function clampPlacement(p: Partial<Placement> | null | undefined): Placement {
  throw new Error("not implemented");
}

/** 角色在畫面中的框：腳底中心在 (x, y)，高度為 scale × 照片高度，寬度依去背圖長寬比。 */
export function characterBox(
  p: Placement,
  display: Display,
  aspect: number,
): { left: number; top: number; width: number; height: number } {
  throw new Error("not implemented");
}
