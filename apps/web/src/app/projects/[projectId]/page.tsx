"use client";

// 選題與企劃確認（架構書 §5.2 確認點 1；spec 0015）
import dynamic from "next/dynamic";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  createVideo,
  getProject,
  getVideo,
  readJson,
  type PlanOut,
  type ProjectOut,
} from "@/api/client";
import { subscribeVideo } from "@/api/events";
import ApprovePanel from "@/components/ApprovePanel";
import PlanCard from "@/components/PlanCard";
import TopicForm from "@/components/TopicForm";
import { buildApproveRequest, createApproveSession } from "@/lib/approve";
import type { Placement } from "@/lib/placement";
import { parsePlan, sellingPointLabels } from "@/lib/plan";

// Konva 依賴瀏覽器 API，只在用戶端載入
const PlacementEditor = dynamic(() => import("@/components/PlacementEditor"), { ssr: false });

type Phase = "idle" | "submitting" | "planning" | "plans";
const DEFAULT_PHOTO = { width: 1080, height: 1920 };

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const router = useRouter();
  const [project, setProject] = useState<ProjectOut | null>(null);
  const [topic, setTopic] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [videoId, setVideoId] = useState<string | null>(null);
  const [plans, setPlans] = useState<PlanOut[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [placements, setPlacements] = useState<Record<number, Placement>>({});
  const [agreed, setAgreed] = useState(false);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const session = useRef(createApproveSession());

  useEffect(() => {
    getProject(projectId).then(setProject, (e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [projectId]);

  useEffect(() => {
    if (!videoId || phase !== "planning") return;
    const close = subscribeVideo(videoId, {
      plan_ready: () => {
        close();
        getVideo(videoId).then(
          (video) => {
            setPlans(video.plans);
            setPhase("plans");
          },
          (e: unknown) => setError(e instanceof Error ? e.message : String(e)),
        );
      },
      planning_failed: () => {
        close();
        setError("企劃產生失敗，請再試一次");
        setPhase("idle");
      },
    });
    return close;
  }, [videoId, phase]);

  const selected = plans.find((p) => p.id === selectedId) ?? null;
  const selectedView = useMemo(() => (selected ? parsePlan(selected.payload) : null), [selected]);

  async function submitTopic() {
    setError(null);
    setPhase("submitting");
    setPlans([]);
    setSelectedId(null);
    try {
      const video = await createVideo(projectId, topic.trim());
      setVideoId(video.id);
      setPhase("planning");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("idle");
    }
  }

  function selectPlan(plan: PlanOut) {
    setSelectedId(plan.id);
    setPlacements(Object.fromEntries(parsePlan(plan.payload).shots.map((s) => [s.shotNo, s.placement])));
    setAgreed(false); // 不同企劃的上限可能不同，需重新同意
    setError(null);
  }

  async function approve() {
    if (!selected || !videoId) return;
    setApproving(true);
    setError(null);
    const req = buildApproveRequest({
      videoId,
      planId: selected.id,
      costCap: selected.estimate.cap,
      placements,
      idempotencyKey: session.current.keyFor(selected.id),
    });
    try {
      await readJson(await fetch(req.url, req.init));
      router.push(`/videos/${videoId}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "無法連線到伺服器，請稍後再試");
      setApproving(false);
    }
  }

  const photo = (id: string | null) => project?.scene_photos.find((p) => p.id === id);

  return (
    <main className="page">
      <header>
        <p className="eyebrow">Tour Reel Studio</p>
        <h1>{project?.name ?? "載入中…"}</h1>
      </header>

      <TopicForm
        topic={topic}
        sellingPoints={sellingPointLabels(project?.brand.selling_points)}
        busy={phase === "submitting" || phase === "planning"}
        onChange={setTopic}
        onSubmit={submitTopic}
      />

      {(phase === "submitting" || phase === "planning") && (
        <p className="status" role="status">
          企劃產生中…
        </p>
      )}

      {phase === "plans" && (
        <section className="plans" aria-label="企劃">
          {plans.map((plan) => (
            <PlanCard key={plan.id} plan={plan} selected={plan.id === selectedId} onSelect={() => selectPlan(plan)} />
          ))}
        </section>
      )}

      {selected && selectedView && (
        <section className="placements" aria-label="角色擺放">
          <h2>調整角色位置與大小</h2>
          <div className="editors">
            {selectedView.shots.map((shot) => {
              const p = photo(shot.scenePhotoId);
              return (
                <PlacementEditor
                  key={`${selected.id}-${shot.shotNo}`}
                  shotNo={shot.shotNo}
                  photoUrl={p?.url}
                  photoSize={p ? { width: p.width, height: p.height } : DEFAULT_PHOTO}
                  cutoutUrl={project?.character?.cutout_url}
                  placement={placements[shot.shotNo] ?? shot.placement}
                  onChange={(next) => setPlacements((prev) => ({ ...prev, [shot.shotNo]: next }))}
                />
              );
            })}
          </div>
          <ApprovePanel
            cap={selected.estimate.cap}
            agreed={agreed}
            busy={approving}
            error={error}
            onAgree={setAgreed}
            onApprove={approve}
          />
        </section>
      )}

      {error && !selected && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </main>
  );
}
