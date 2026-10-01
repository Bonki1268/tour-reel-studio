// 企劃 payload（後端為未定型 JSON）轉為畫面資料；品牌賣點標籤（spec 0015 R-002、R-003）
import { clampPlacement, type Placement } from "./placement";

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

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const text = (v: unknown, fallback: string) => (typeof v === "string" && v.trim() ? v : fallback);
const number = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);

export function parsePlan(payload: unknown): PlanView {
  if (!isObj(payload)) return { title: "—", concept: "—", shots: [] };
  const shots = Array.isArray(payload.shots) ? payload.shots : [];
  return {
    title: text(payload.title, "—"),
    concept: text(payload.concept, "—"),
    shots: shots.map((raw, i) => {
      const s = isObj(raw) ? raw : {};
      return {
        shotNo: number(s.shot_no) ?? i + 1,
        role: text(s.role, "—"),
        durationS: number(s.duration_s),
        scenePhotoId: typeof s.scene_photo_id === "string" ? s.scene_photo_id : null,
        placement: clampPlacement(isObj(s.placement) ? (s.placement as Partial<Placement>) : null),
        action: text(s.action, "—"),
        subtitle: typeof s.subtitle === "string" ? s.subtitle : "",
      };
    }),
  };
}

/** 品牌賣點：字串或物件的 title；略過空值與其他型別。 */
export function sellingPointLabels(points: unknown): string[] {
  if (!Array.isArray(points)) return [];
  return points
    .map((p) => (typeof p === "string" ? p : isObj(p) && typeof p.title === "string" ? p.title : ""))
    .map((label) => label.trim())
    .filter(Boolean);
}

/** 把賣點加入主題：空白時直接填入，否則以「、」接上；已包含時不重複。 */
export function appendTopic(current: string, label: string): string {
  const base = current.trim();
  if (!base) return label;
  return base.split("、").includes(label) ? base : `${base}、${label}`;
}
