"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

type StanceAccent = "BUY" | "WATCH" | "REJECT";

const STANCE_STRIPE_CLASS: Record<StanceAccent, string> = {
  BUY: "before:bg-red-500",
  WATCH: "before:bg-amber-500",
  REJECT: "before:bg-blue-500",
};

/**
 * Common 7-section shell — header, compact body, expandable expanded body,
 * and a per-section source list slot.
 *
 * Plan §7.4. Default-open mirrors spec D3 (only 종합의견 + 의사결정 default open;
 * caller passes `defaultOpen={true}` for those).
 */
export function SectionShell({
  emoji,
  title,
  defaultOpen = false,
  highlight,
  stanceAccent,
  compact,
  expanded,
  sources,
}: {
  emoji: string;
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
}) {
  const [open, setOpen] = useState(defaultOpen);

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
      className={`relative rounded-xl border border-[var(--surface-border)] ${surfaceClass} ${stripeClass} overflow-hidden`}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left min-h-11 hover:bg-[var(--surface-section-hover)]/50 transition-colors"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2.5 min-w-0 flex-1">
          <span aria-hidden className="text-base shrink-0">{emoji}</span>
          <span className="font-semibold text-[var(--surface-text)] shrink-0">
            {title}
          </span>
          <span className="text-sm text-[var(--surface-text-muted)] truncate min-w-0 flex-1">
            {compact}
          </span>
        </span>
        <span className="shrink-0 text-[var(--surface-text-subtle)]">
          {open ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        </span>
      </button>
      {open && expanded ? (
        <div className="border-t border-[var(--surface-border)] px-4 py-3">
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
