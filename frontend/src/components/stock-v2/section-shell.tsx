"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight, HelpCircle } from "lucide-react";

type StanceAccent = "BUY" | "WATCH" | "REJECT";

const STANCE_STRIPE_CLASS: Record<StanceAccent, string> = {
  BUY: "before:bg-red-500",
  WATCH: "before:bg-amber-500",
  REJECT: "before:bg-blue-500",
};

/**
 * Common 7-section shell — header, compact body, expandable expanded body,
 * a per-section source list slot, and an optional "?" help popover.
 *
 * 2026-05-14 사용자 피드백: "처음 보는 사람이 모멘텀? 그게뭐지 이건 뭔
 * 숫자지 이런걸 모를거같아 뭐 진짜 주식 개 고수면 모를까". 모든 섹션
 * header 에 helpText prop 으로 "?" 도움말 토글. 클릭 시 popover.
 *
 * Plan §7.4 + feedback_card_user_facing_copy.
 */
export function SectionShell({
  emoji,
  icon,
  title,
  defaultOpen = false,
  highlight,
  stanceAccent,
  compact,
  expanded,
  sources,
  helpText,
}: {
  emoji?: string;
  icon?: ReactNode;
  title: string;
  defaultOpen?: boolean;
  /** Optional surface-token key for emphasized sections (glance / decision). */
  highlight?: "glance" | "decision";
  /** When set, draws a stance-colored 4px left accent stripe and uses the shared
   *  emphasized surface (`--surface-glance`). Used by 종합 의견 + 의사결정 so the
   *  two visually group as the "what should I do?" pane. */
  stanceAccent?: StanceAccent;
  /** 1-line summary always visible. */
  compact: ReactNode;
  /** Drill-down content shown when expanded. */
  expanded?: ReactNode;
  /** Per-section source list — rendered below `expanded` when open. */
  sources?: ReactNode;
  /** 가족 비전공자 친화 도움말. ReactNode 라 강조/리스트도 가능. */
  helpText?: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [helpOpen, setHelpOpen] = useState(false);

  const surfaceClass = stanceAccent
    ? "bg-[var(--surface-glance)]"
    : highlight === "glance"
      ? "bg-[var(--surface-glance)]"
      : highlight === "decision"
        ? "bg-[var(--surface-decision)]"
        : "bg-[var(--surface-section)]";

  const stripeClass = stanceAccent
    ? `before:absolute before:left-0 before:top-3 before:bottom-3 before:w-1 before:rounded-r before:content-[''] ${STANCE_STRIPE_CLASS[stanceAccent]}`
    : "";

  return (
    <section
      className={`relative rounded-lg border border-[var(--surface-border)] ${surfaceClass} ${stripeClass} overflow-hidden`}
    >
      <div className="flex w-full items-stretch">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="grid min-h-14 flex-1 grid-cols-[22px_minmax(72px,auto)_minmax(0,1fr)_18px] items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-[var(--surface-section-hover)]/50 sm:min-h-11 sm:grid-cols-[22px_auto_minmax(0,1fr)_18px] sm:px-4 sm:py-3"
          aria-expanded={open}
        >
          <span
            aria-hidden
            className="inline-flex size-[22px] items-center justify-center text-[var(--surface-text-muted)]"
          >
            {icon ?? <span className="text-base">{emoji}</span>}
          </span>
          <span className="whitespace-nowrap text-sm font-semibold leading-none text-[var(--surface-text)] sm:text-[15px]">
            {title}
          </span>
          <span className="min-w-0 truncate text-xs leading-none text-[var(--surface-text-muted)] sm:text-sm">
            {compact}
          </span>
          <span className="inline-flex justify-end text-[var(--surface-text-subtle)]">
            {open ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
          </span>
        </button>
        {helpText ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setHelpOpen((v) => !v);
            }}
            aria-label={`${title} 도움말`}
            title="이 섹션이 뭔지 설명 보기"
            className={`relative inline-flex min-h-14 w-10 shrink-0 items-center justify-center border-l border-[var(--surface-border)] transition-colors sm:min-h-11 ${
              helpOpen
                ? "bg-blue-500/10 text-blue-700 dark:text-blue-300"
                : "text-[var(--surface-text-subtle)] hover:text-[var(--surface-text-muted)] hover:bg-[var(--surface-section-hover)]/50"
            }`}
          >
            <HelpCircle size={16} />
          </button>
        ) : null}
      </div>
      {helpText && helpOpen ? (
        <div className="border-t border-blue-500/30 bg-blue-500/5 px-4 py-3 text-xs leading-relaxed text-[var(--surface-text)]">
          {helpText}
        </div>
      ) : null}
      {open && expanded ? (
        <div className="border-t border-[var(--surface-border)] px-3 py-3 sm:px-4">
          {expanded}
          {sources ? (
            <div className="mt-3 border-t border-[var(--surface-border)] pt-3 text-xs text-[var(--surface-text-muted)]">
              {sources}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
