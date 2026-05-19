"use client";

import { FileText } from "lucide-react";
import type { Citation, Claim, Stance, Thesis } from "@/types/card";
import { CitationList } from "./citation-ref";
import { SectionShell } from "./section-shell";

const SCENARIO_BAR_COLOR = {
  BULL: "bg-emerald-500",
  BASE: "bg-blue-500",
  BEAR: "bg-rose-500",
} as const;

const SCENARIO_LABEL = {
  BULL: "좋은 경우",
  BASE: "기본 경우",
  BEAR: "나쁜 경우",
} as const;

export function ThesisSection({
  thesis,
  stance,
  citations,
}: {
  thesis: Thesis;
  stance: Stance;
  citations: Citation[];
}) {
  const supportCount = thesis.supports?.length ?? 0;
  const opposeCount = thesis.opposes?.length ?? 0;
  const baseScenario = thesis.scenarios?.find((s) => s.name === "BASE");
  const basePct = baseScenario ? Math.round(baseScenario.probability * 100) : null;
  const catalystCount = thesis.catalysts?.length ?? 0;

  const compactParts: string[] = [];
  compactParts.push(`긍정 ${supportCount}`);
  compactParts.push(`반대 ${opposeCount}`);
  if (basePct !== null) compactParts.push(`기본 경우 ${basePct}%`);
  compactParts.push(catalystCount > 0 ? `예정 이벤트 ${catalystCount}건` : "임박 일정 없음");

  return (
    <SectionShell
      icon={<FileText size={17} />}
      title="종합 의견"
      defaultOpen
      stanceAccent={stance}
      compact={<span>{compactParts.join(" · ")}</span>}
      expanded={<ThesisExpanded thesis={thesis} citations={citations} />}
    />
  );
}

function ThesisExpanded({
  thesis,
  citations,
}: {
  thesis: Thesis;
  citations: Citation[];
}) {
  return (
    <div className="space-y-4 text-sm">
      <p className="font-medium leading-relaxed">
        {thesis.core_thesis}
        <CitationList ids={thesis.citations} citations={citations} className="ml-1" />
      </p>

      <ClaimList
        label="긍정 근거"
        labelClass="text-red-700 dark:text-red-400"
        claims={thesis.supports}
        citations={citations}
      />
      <ClaimList
        label="반대 근거"
        labelClass="text-blue-700 dark:text-blue-400"
        claims={thesis.opposes}
        citations={citations}
      />

      {thesis.scenarios.length > 0 ? (
        <div>
          <div className="text-xs font-semibold mb-1.5">앞으로 가능한 경우</div>
          <div className="space-y-1.5">
            {thesis.scenarios.map((s, i) => {
              const pct = Math.round(s.probability * 100);
              return (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-xs font-medium w-16">{SCENARIO_LABEL[s.name]}</span>
                  <div className="flex-1 h-2 bg-[var(--surface-section)] rounded overflow-hidden">
                    <div
                      className={`h-full ${SCENARIO_BAR_COLOR[s.name]}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-xs w-10 text-right tabular-nums">{pct}%</span>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {thesis.catalysts.length > 0 ? (
        <div>
          <div className="text-xs font-semibold mb-1">14일 내 예정 이벤트</div>
          <ul className="space-y-1 text-xs text-[var(--surface-text-muted)]">
            {thesis.catalysts.map((c, i) => (
              <li key={i}>
                · <span className="font-medium text-[var(--surface-text)]">{c.when}</span> — {c.event}
                <CitationList ids={c.citation_ids} citations={citations} className="ml-1" />
              </li>
            ))}
          </ul>
        </div>
      ) : thesis.no_catalysts_reason ? (
        <p className="text-xs italic text-[var(--surface-text-subtle)]">
          확인된 임박 일정 없음 — {thesis.no_catalysts_reason}
        </p>
      ) : null}
    </div>
  );
}

function ClaimList({
  label,
  labelClass,
  claims,
  citations,
}: {
  label: string;
  labelClass: string;
  claims: Claim[];
  citations: Citation[];
}) {
  if (claims.length === 0) return null;
  return (
    <div>
      <div className={`text-xs font-semibold mb-1 ${labelClass}`}>{label}</div>
      <ul className="space-y-1 list-disc list-inside text-[var(--surface-text-muted)]">
        {claims.map((c, i) => (
          <li key={i}>
            {c.text}
            <CitationList ids={c.citations} citations={citations} className="ml-1" />
          </li>
        ))}
      </ul>
    </div>
  );
}
