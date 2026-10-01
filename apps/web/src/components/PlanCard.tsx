"use client";

import type { PlanOut } from "@/api/client";
import { formatCredits } from "@/lib/format";
import { parsePlan } from "@/lib/plan";

const ROLE_LABEL: Record<string, string> = { hook: "鉤子", feature: "特色", cta: "行動呼籲" };

type Props = { plan: PlanOut; selected: boolean; onSelect: () => void };

export default function PlanCard({ plan, selected, onSelect }: Props) {
  const view = parsePlan(plan.payload);
  return (
    <article data-testid="plan-card" className={selected ? "plan-card selected" : "plan-card"}>
      <h3>{view.title}</h3>
      <p className="concept">{view.concept}</p>
      <ol className="shots">
        {view.shots.map((s) => (
          <li key={s.shotNo} data-testid="shot-summary">
            <strong>
              第 {s.shotNo} 鏡・{ROLE_LABEL[s.role] ?? s.role}
              {s.durationS !== null && `・${s.durationS} 秒`}
            </strong>
            <span>{s.action}</span>
            {s.subtitle && <span className="subtitle">「{s.subtitle}」</span>}
          </li>
        ))}
      </ol>
      <dl className="estimate">
        <dt>預估點數</dt>
        <dd data-testid="estimate-total">{formatCredits(plan.estimate.total)}</dd>
        <dt>預留重生額度</dt>
        <dd data-testid="estimate-reserve">{formatCredits(plan.estimate.reserve)}</dd>
        <dt>成本上限</dt>
        <dd data-testid="estimate-cap">{formatCredits(plan.estimate.cap)}</dd>
      </dl>
      <button type="button" onClick={onSelect} aria-pressed={selected}>
        選擇此企劃
      </button>
    </article>
  );
}
