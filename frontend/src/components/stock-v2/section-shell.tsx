"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

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
  compact,
  expanded,
  sources,
}: {
  emoji: string;
  title: string;
  defaultOpen?: boolean;
  /** Optional surface-token key for emphasized sections (glance / decision). */
  highlight?: "glance" | "decision";
  /** 1-line summary always visible. */
  compact: ReactNode;
  /** Drill-down content shown when expanded. */
  expanded?: ReactNode;
  /** Per-section source list — rendered below `expanded` when open. */
  sources?: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  const highlightClass =
    highlight === "glance"
      ? "bg-[var(--surface-glance)]"
      : highlight === "decision"
        ? "bg-[var(--surface-decision)]"
        : "bg-[var(--surface-section)]";

  return (
    <section
      className={`rounded-md border border-[var(--surface-border)] ${highlightClass} mb-3`}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-3 text-left min-h-11"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2 text-base md:text-sm font-medium">
          <span aria-hidden>{emoji}</span>
          <span>{title}</span>
        </span>
        {open ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
      </button>
      <div className="px-4 pb-3 text-sm text-[var(--surface-text-muted)]">
        {compact}
      </div>
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
