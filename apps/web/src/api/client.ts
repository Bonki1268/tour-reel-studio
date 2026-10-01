// 後端 API（同源 /api 代理）；型別由 OpenAPI 產生（npm run gen:api）
import type { components } from "./schema";

export type ProjectOut = components["schemas"]["ProjectOut"];
export type VideoOut = components["schemas"]["VideoOut"];
export type PlanOut = components["schemas"]["PlanOut"];
export type ScenePhotoOut = components["schemas"]["ScenePhotoOut"];

export class ApiError extends Error {}

/** 讀取回應；失敗時以後端的 message 拋出 ApiError。 */
export async function readJson<T>(response: Response): Promise<T> {
  if (response.ok) return (await response.json()) as T;
  let message = "發生錯誤，請稍後再試";
  try {
    const body = (await response.json()) as { message?: unknown };
    if (typeof body.message === "string" && body.message) message = body.message;
  } catch {
    // 非 JSON 回應：使用預設訊息
  }
  throw new ApiError(message);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, init);
  } catch {
    throw new ApiError("無法連線到伺服器，請稍後再試");
  }
  return readJson<T>(response);
}

export const getProject = (projectId: string) => request<ProjectOut>(`/projects/${encodeURIComponent(projectId)}`);

export const createVideo = (projectId: string, topic: string) =>
  request<VideoOut>(`/projects/${encodeURIComponent(projectId)}/videos`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic }),
  });

export const getVideo = (videoId: string) => request<VideoOut>(`/videos/${encodeURIComponent(videoId)}`);
