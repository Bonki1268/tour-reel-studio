"use client";

import { formatCredits } from "@/lib/format";
import type { ShotProgress as Progress, ShotState } from "@/lib/progress";

const LABEL: Record<ShotState, string> = { waiting: "等待中", running: "生成中", done: "完成", failed: "失敗" };
const ROLE: Record<string, string> = { hook: "鉤子", feature: "特色", cta: "行動呼籲" };

type Props = {
  shotNo: number;
  role?: string;
  progress: Progress;
  canRegenerate: boolean;
  busy: boolean;
  onRegenerate: () => void;
};

export default function ShotProgress({ shotNo, role, progress, canRegenerate, busy, onRegenerate }: Props) {
  return (
    <li data-testid={`shot-${shotNo}`} className={`shot-progress ${progress.state}`}>
      <strong>
        第 {shotNo} 鏡{role ? `・${ROLE[role] ?? role}` : ""}
      </strong>
      <span className="state">{LABEL[progress.state]}</span>
      {progress.state === "failed" && progress.reason && <span className="reason">{progress.reason}</span>}
      {canRegenerate && (
        <span className="regen">
          <button type="button" disabled={busy} onClick={onRegenerate}>
            重生
          </button>
          <span data-testid="regen-cost">{formatCredits(progress.regenCost)}</span>
        </span>
      )}
    </li>
  );
}
