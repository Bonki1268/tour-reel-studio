"use client";

// 生成進度與成品確認（架構書 §5.2 確認點 2；spec 0016）
import { useParams } from "next/navigation";
import { useCallback, useEffect, useReducer, useState } from "react";
import { approveFinal, getDownload, getVideo, regenerateShot, type VideoOut } from "@/api/client";
import { subscribeWithReconnect } from "@/api/reconnect";
import RegenDialog from "@/components/RegenDialog";
import ResultPanel from "@/components/ResultPanel";
import ShotProgress from "@/components/ShotProgress";
import { needsConfirmation, newCap, remaining } from "@/lib/budget";
import { formatCredits } from "@/lib/format";
import { initialState, reduce } from "@/lib/progress";

const STATUS_LABEL: Record<string, string> = {
  generating: "生成中",
  rendering: "合成中",
  review: "成品確認",
  needs_attention: "需要處理",
  approved: "成品已確認",
};

export default function VideoPage() {
  const { videoId } = useParams<{ videoId: string }>();
  const [state, dispatch] = useReducer(reduce, initialState);
  const [roles, setRoles] = useState<Record<number, string>>({});
  const [confirming, setConfirming] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const applyVideo = useCallback((video: VideoOut) => {
    dispatch({ type: "snapshot", video });
    setRoles(Object.fromEntries(video.shots.map((s) => [s.shot_no, s.role])));
  }, []);

  const refresh = useCallback(() => {
    getVideo(videoId).then(applyVideo, (e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [videoId, applyVideo]);

  useEffect(() => {
    refresh();
    return subscribeWithReconnect(videoId, {
      onEvent: (event) => {
        dispatch({ type: "event", event });
        if (event.type === "review_ready") refresh(); // 取得成品的預簽名網址
      },
      onConnection: (connection) => dispatch({ type: "connection", state: connection }),
      onReconnected: refresh,
    });
  }, [videoId, refresh]);

  const left = remaining(state.costCap, state.spent);

  async function run(action: () => Promise<VideoOut | void>) {
    setBusy(true);
    setError(null);
    try {
      const video = await action();
      if (video) applyVideo(video);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function onRegenerate(shotNo: number) {
    const cost = state.shots[shotNo]?.regenCost ?? "0";
    if (needsConfirmation(cost, left)) setConfirming(shotNo);
    else void run(() => regenerateShot(videoId, shotNo));
  }

  async function onDownload() {
    if (state.status === "approved") {
      await run(async () => {
        const { url } = await getDownload(videoId);
        window.open(url, "_blank", "noopener");
      });
    } else if (state.previewUrl) {
      window.open(state.previewUrl, "_blank", "noopener");
    }
  }

  const shotNos = Object.keys(state.shots).map(Number).sort((a, b) => a - b);
  const canRegenerate = (no: number) =>
    state.status === "review" || (state.status === "needs_attention" && state.shots[no]?.state === "failed");

  return (
    <main className="page">
      <h1>生成進度</h1>
      <p className="overall" data-testid="video-status">
        {STATUS_LABEL[state.status] ?? state.status}
      </p>
      {state.connection === "lost" && (
        <p role="status" className="warning">
          連線中斷，重新連線中…
        </p>
      )}
      <dl className="budget">
        <dt>剩餘預算</dt>
        <dd data-testid="remaining-budget">{left === null ? "—" : formatCredits(left)}</dd>
      </dl>
      <ol className="shot-list">
        {shotNos.map((no) => (
          <ShotProgress
            key={no}
            shotNo={no}
            role={roles[no]}
            progress={state.shots[no]}
            canRegenerate={canRegenerate(no)}
            busy={busy}
            onRegenerate={() => onRegenerate(no)}
          />
        ))}
      </ol>
      {state.status === "rendering" && <p role="status">3 鏡已完成，正在合成成品…</p>}
      {state.previewUrl && (state.status === "review" || state.status === "approved") && (
        <ResultPanel
          status={state.status}
          previewUrl={state.previewUrl}
          busy={busy}
          onDownload={onDownload}
          onApprove={() => void run(() => approveFinal(videoId))}
        />
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {confirming !== null && (
        <RegenDialog
          shotNo={confirming}
          remaining={left}
          cost={state.shots[confirming]?.regenCost ?? "0"}
          newCap={newCap(state.spent, state.shots[confirming]?.regenCost ?? "0")}
          busy={busy}
          onCancel={() => setConfirming(null)}
          onConfirm={() => {
            const shotNo = confirming;
            setConfirming(null);
            void run(() => regenerateShot(videoId, shotNo, newCap(state.spent, state.shots[shotNo]?.regenCost ?? "0")));
          }}
        />
      )}
    </main>
  );
}
