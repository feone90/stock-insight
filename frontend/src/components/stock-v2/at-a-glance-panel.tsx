"use client";

import type { StockCard } from "@/types/card";

const GRADE_FG = {
  S: "text-[#7c3aed] dark:text-[#a78bfa]",
  A: "text-[#0a8f3d] dark:text-[#4ade80]",
  B: "text-[#0891b2] dark:text-[#22d3ee]",
  C: "text-[#a06800] dark:text-[#fbbf24]",
  D: "text-[#c81e1e] dark:text-[#f87171]",
} as const;

const STANCE_LABEL = {
  BUY: "매수 후보",
  WATCH: "관망",
  REJECT: "보류",
} as const;

const ENTRY_STAGE_LABEL = {
  ENTER: "진입 시점",
  WAIT: "대기",
  REJECT: "보류",
} as const;

/**
 * At-a-glance panel — Final Grade · Stance · Entry Stage 3 tile + one-line
 * summary. Plan §7.3.
 */
export function AtAGlancePanel({ card }: { card: StockCard }) {
  const g = card.glance;
  const deltaIcon =
    g.grade_delta === "up" ? "↑" : g.grade_delta === "down" ? "↓" : "";

  return (
    <div className="border-b border-[var(--surface-border)] bg-[var(--surface-glance)] p-4">
      <div className="grid grid-cols-3 gap-3">
        <Tile label="Final Grade">
          <span className={`text-3xl md:text-4xl font-bold ${GRADE_FG[g.final_grade]}`}>
            {g.final_grade}
            {deltaIcon ? <span className="ml-1 text-base">{deltaIcon}</span> : null}
          </span>
        </Tile>
        <Tile label="Stance">
          <span className="text-lg md:text-xl font-semibold">
            {STANCE_LABEL[g.stance]}
          </span>
        </Tile>
        <Tile label="Entry Stage">
          <span className="text-lg md:text-xl font-semibold">
            {ENTRY_STAGE_LABEL[g.entry_stage]}
          </span>
        </Tile>
      </div>
      <p className="mt-3 text-base md:text-sm text-[var(--surface-text)]">
        {g.one_line}
      </p>
    </div>
  );
}

function Tile({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-[var(--surface-border)] bg-[var(--surface-card)] p-3 text-center">
      <div className="text-xs text-[var(--surface-text-muted)] mb-1">{label}</div>
      {children}
    </div>
  );
}
