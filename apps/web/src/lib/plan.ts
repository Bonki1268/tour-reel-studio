// 企劃 payload（後端為未定型 JSON）轉為畫面資料；品牌賣點標籤（spec 0015 R-002、R-003）
import type { Placement } from "./placement";

export type ShotView = {
  shotNo: number;
  role: string;
  durationS: number | null;
  scenePhotoId: string | null;
  placement: Placement;
  action: string;
  subtitle: string;
};

export type PlanView = { title: string; concept: string; shots: ShotView[] };

export function parsePlan(payload: unknown): PlanView {
  throw new Error("not implemented");
}

export function sellingPointLabels(points: unknown): string[] {
  throw new Error("not implemented");
}

export function appendTopic(current: string, label: string): string {
  throw new Error("not implemented");
}
