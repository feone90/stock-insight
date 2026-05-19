"use client";

import { CheckCircle2 } from "lucide-react";
import type { Citation, Decision } from "@/types/card";
import { CitationList } from "./citation-ref";
import { SectionShell } from "./section-shell";

const STANCE_LABEL = {
  BUY: "매수 후보",
  WATCH: "관망",
  REJECT: "보류",
} as const;

export function DecisionSection({
  decision,
  citations,
}: {
  decision: Decision;
  citations: Citation[];
}) {
  const parts: string[] = [STANCE_LABEL[decision.stance]];
  if (decision.support_price != null)
    parts.push(`지지선 ${decision.support_price.toLocaleString()}`);
  if (decision.risk_threshold != null)
    parts.push(`리스크 ${decision.risk_threshold.toLocaleString()}`);

  return (
    <SectionShell
      icon={<CheckCircle2 size={17} />}
      title="의사결정"
      defaultOpen
      stanceAccent={decision.stance}
      compact={<span>{parts.join(" · ")}</span>}
      expanded={<DecisionExpanded decision={decision} citations={citations} />}
    />
  );
}

function DecisionExpanded({
  decision,
  citations,
}: {
  decision: Decision;
  citations: Citation[];
}) {
  return (
    <div className="space-y-3 text-sm">
      {decision.sizing_note ? (
        <p className="font-medium leading-relaxed">
          {decision.sizing_note}
          <CitationList ids={decision.citations} citations={citations} className="ml-1" />
        </p>
      ) : (
        <div className="text-sm">
          <CitationList ids={decision.citations} citations={citations} />
        </div>
      )}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <div className="flex justify-between">
          <dt className="text-[var(--surface-text-muted)]">판단</dt>
          <dd>{STANCE_LABEL[decision.stance]}</dd>
        </div>
        {decision.support_price != null ? (
          <div className="flex justify-between">
            <dt className="text-[var(--surface-text-muted)]">기준 지지선</dt>
            <dd className="tabular-nums">
              {decision.support_price.toLocaleString()}
            </dd>
          </div>
        ) : null}
        {decision.risk_threshold != null ? (
          <div className="flex justify-between">
            <dt className="text-[var(--surface-text-muted)]">리스크 임계</dt>
            <dd className="tabular-nums">
              {decision.risk_threshold.toLocaleString()}
            </dd>
          </div>
        ) : null}
      </dl>

      <p className="text-xs italic text-[var(--surface-text-subtle)]">
        {decision.note || "참고용 — 투자 권유 아님"}
      </p>
    </div>
  );
}
