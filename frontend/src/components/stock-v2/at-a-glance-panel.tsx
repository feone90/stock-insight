"use client";

import type { StockCard } from "@/types/card";
import { CitationList } from "./citation-ref";

const GRADE_FG = {
  S: "text-violet-600 dark:text-violet-400",
  A: "text-red-600 dark:text-red-400",
  B: "text-cyan-600 dark:text-cyan-400",
  C: "text-amber-600 dark:text-amber-400",
  D: "text-blue-600 dark:text-blue-400",
} as const;

const STANCE_LABEL = {
  BUY: "매수 후보",
  WATCH: "관망",
  REJECT: "보류",
} as const;

const ENTRY_STAGE_LABEL = {
  ENTER: "진입",
  WAIT: "대기",
  REJECT: "보류",
} as const;

const DELTA_LABEL = {
  up: "↑ 상승",
  down: "↓ 하락",
  same: "→ 동일",
} as const;

/**
 * At-a-glance panel — Final Grade + Stance + Entry Stage stacked, with the
 * one-line summary as the dominant text. Lives in the right column on desktop
 * so the user sees "what should I do?" without scrolling.
 *
 * Plan §7.3 + post-A design pass.
 */
export function AtAGlancePanel({ card }: { card: StockCard }) {
  const g = card.glance;
  const deltaLabel = g.grade_delta ? DELTA_LABEL[g.grade_delta] : null;

  return (
    <div className="rounded-xl border border-[var(--surface-border)] bg-[var(--surface-glance)] p-4 md:p-5">
      <div className="flex items-baseline justify-between gap-3 mb-3">
        <span className="text-xs font-medium uppercase tracking-wide text-[var(--surface-text-muted)]">
          종합 판단
        </span>
        <span className="text-xs text-[var(--surface-text-subtle)]">
          한눈 보기
        </span>
      </div>

      <div className="flex items-end gap-4">
        <div>
          <div className="text-xs text-[var(--surface-text-muted)] mb-0.5">
            종합 등급
          </div>
          <div className={`text-5xl font-extrabold leading-none ${GRADE_FG[g.final_grade]}`}>
            {g.final_grade}
          </div>
          {deltaLabel ? (
            <div className="mt-1 text-xs text-[var(--surface-text-muted)]">
              어제 대비 {deltaLabel}
            </div>
          ) : null}
        </div>

        <div className="flex-1 grid grid-cols-2 gap-2 pl-3 border-l border-[var(--surface-border)]">
          <div>
            <div className="text-xs text-[var(--surface-text-muted)] mb-0.5">
              판단
            </div>
            <div className="text-base font-semibold">{STANCE_LABEL[g.stance]}</div>
          </div>
          <div>
            <div className="text-xs text-[var(--surface-text-muted)] mb-0.5">
              진입
            </div>
            <div className="text-base font-semibold">
              {ENTRY_STAGE_LABEL[g.entry_stage]}
            </div>
          </div>
        </div>
      </div>

      <p className="mt-4 text-base md:text-[15px] leading-relaxed text-[var(--surface-text)]">
        {g.one_line}
        <CitationList ids={g.citations} citations={card.citations} className="ml-1" />
      </p>
    </div>
  );
}
