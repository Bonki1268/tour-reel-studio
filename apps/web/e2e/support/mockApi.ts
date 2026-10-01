// 以 page.route 模擬後端 /api/*（spec 0015）：記錄前端送出的請求，SSE 事件由步驟控制送出時機
import type { Page, Request, Route } from "@playwright/test";
import { CUTOUT_PNG, PHOTO_PNG } from "./images";

export const PROJECT_ID = "demo";
export const VIDEO_ID = "v1";

const photos = [1, 2, 3].map((n) => ({
  id: `photo-${n}`,
  image_key: `projects/demo/scenes/photo-${n}.jpg`,
  width: 1080,
  height: 1920,
  description: ["梅園入口", "採梅步道", "梅子醋工坊"][n - 1],
  url: `/mock-assets/photo-${n}.png`,
}));

export const project = {
  id: PROJECT_ID,
  name: "梅子農場",
  brand: {
    visual: { colors: ["#6B8E23"] },
    selling_points: ["手作早餐", { title: "親子採果", season: [3, 4] }],
    tone: "溫暖、在地",
    info: { address: "台南市楠西區" },
  },
  character: { id: "c1", version: 1, anchor_card: { name: "梅子阿伯" }, cutout_url: "/mock-assets/cutout.png" },
  scene_photos: photos,
};

function shot(no: number, placement: { x: number; y: number; scale: number; flip: boolean }) {
  return {
    shot_no: no,
    role: ["hook", "feature", "cta"][no - 1],
    duration_s: [4, 5, 3][no - 1],
    scene_photo_id: `photo-${no}`,
    placement,
    action: ["向鏡頭揮手", "品嚐梅子醋", "邀請大家來玩"][no - 1],
    subtitle: ["早安，梅子農場！", "手工梅子醋", "週末來採梅！"][no - 1],
  };
}

export const plans = [
  { id: "plan-1", cap: "40" },
  { id: "plan-2", cap: "1234.5" },
  { id: "plan-3", cap: "52" },
].map(({ id, cap }, i) => ({
  id,
  payload: {
    title: ["梅香晨光", "親子採梅日", "職人梅子醋"][i],
    concept: "清晨的梅園裡，梅子阿伯帶大家體驗採梅",
    tone: "溫暖",
    shots: [
      shot(1, { x: 0.3, y: 0.6, scale: 0.4, flip: false }),
      shot(2, { x: 0.5, y: 0.85, scale: 0.5, flip: false }),
      shot(3, { x: 0.6, y: 0.9, scale: 0.45, flip: true }),
    ],
  },
  estimate: { total: String(Number(cap) - 10), reserve: "10", cap },
}));

function video(status: string) {
  return {
    id: VIDEO_ID,
    project_id: PROJECT_ID,
    status,
    topic: "清晨採梅體驗",
    plans: status === "planning" ? [] : plans,
    selected_plan_id: status === "generating" ? "plan-1" : null,
    shots: [],
    cost_cap: null,
    spent: "0",
    preview_url: null,
  };
}

export type Recorded = { headers: Record<string, string>; body: unknown };

export class MockApi {
  createBody: unknown = undefined;
  approve: Recorded | undefined = undefined;
  private status = "planning";
  private releasePlanReady: () => void = () => {};
  private planReady = new Promise<void>((resolve) => (this.releasePlanReady = resolve));

  async install(page: Page): Promise<void> {
    await page.route("**/mock-assets/*.png", (route) =>
      route.fulfill({ contentType: "image/png", body: route.request().url().includes("cutout") ? CUTOUT_PNG : PHOTO_PNG }),
    );
    await page.route("**/api/**", (route, request) => this.handle(route, request));
  }

  /** 送出 SSE 事件（目前只支援 plan_ready）。 */
  emit(event: string): void {
    if (event !== "plan_ready") throw new Error(`mock 不支援事件 ${event}`);
    this.status = "plan_ready";
    this.releasePlanReady();
  }

  private async handle(route: Route, request: Request): Promise<void> {
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api/, "");
    const method = request.method();
    if (method === "GET" && path === `/projects/${PROJECT_ID}`) {
      return route.fulfill({ json: project });
    }
    if (method === "POST" && path === `/projects/${PROJECT_ID}/videos`) {
      this.createBody = request.postDataJSON();
      return route.fulfill({ status: 201, json: video("planning") });
    }
    if (method === "GET" && path === `/videos/${VIDEO_ID}/events`) {
      await this.planReady;
      const data = { type: "plan_ready", video_id: VIDEO_ID, at: new Date().toISOString(), shot_no: null,
        data: { plan_ids: plans.map((p) => p.id) } };
      const body = `event: status\ndata: ${JSON.stringify({ type: "status", status: "plan_ready" })}\n\n`
        + `event: plan_ready\ndata: ${JSON.stringify(data)}\n\n`;
      return route.fulfill({ status: 200, contentType: "text/event-stream", body });
    }
    if (method === "GET" && path === `/videos/${VIDEO_ID}`) {
      return route.fulfill({ json: video(this.status) });
    }
    if (method === "POST" && path === `/videos/${VIDEO_ID}/approve-plan`) {
      this.approve = { headers: await request.allHeaders(), body: request.postDataJSON() };
      this.status = "generating";
      return route.fulfill({ status: 202, json: video("generating") });
    }
    return route.fulfill({ status: 404, json: { code: "not_found", message: `mock 沒有 ${method} ${path}` } });
  }
}
