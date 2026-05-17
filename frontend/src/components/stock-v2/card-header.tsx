"use client";

import { currencyMark } from "@/lib/markets";
import type { StockCard } from "@/types/card";

const STANCE_LABEL = {
  BUY: "매수 후보",
  WATCH: "관망",
  REJECT: "보류",
} as const;

const STANCE_BG = {
  BUY: "bg-red-500/15 text-red-700 dark:bg-red-500/20 dark:text-red-300 border-red-500/30",
  WATCH:
    "bg-amber-500/15 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300 border-amber-500/30",
  REJECT: "bg-blue-500/15 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300 border-blue-500/30",
} as const;

/**
 * Card header — ticker + names + market + tags + stance badge + price + asof.
 * Spans full card width. Plan §7.1 + post-A design pass.
 */
export function CardHeader({ card }: { card: StockCard }) {
  const change = card.change ?? 0;
  const changePct = card.change_pct ?? 0;
  const sign = change > 0 ? "+" : "";
  const changeColor =
    change > 0
      ? "text-red-600 dark:text-red-400"
      : change < 0
        ? "text-blue-600 dark:text-blue-400"
        : "text-[var(--surface-text-muted)]";
  const mark = currencyMark(card.market);

  const asofAbsolute = card.asof
    ? new Date(card.asof).toLocaleString("ko-KR", {
        dateStyle: "short",
        timeStyle: "short",
      })
    : "—";
  const asofRelative = card.asof ? _formatRelative(new Date(card.asof)) : "";

  return (
    <header className="px-5 md:px-6 pt-5 md:pt-6 pb-4 md:pb-5 border-b border-[var(--surface-border)]">
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        {/* Left: identity + tags + stance */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="text-2xl md:text-3xl font-bold tracking-tight">
              {card.name_ko || card.ticker}
            </span>
            <span className="text-base md:text-lg font-mono text-[var(--surface-text-muted)]">
              {card.ticker}
            </span>
            {card.market ? (
              <span className="text-xs font-medium px-1.5 py-0.5 rounded border border-[var(--surface-border)] text-[var(--surface-text-muted)]">
                {card.market}
              </span>
            ) : null}
          </div>
          {card.name_en ? (
            <div className="mt-0.5 text-sm text-[var(--surface-text-subtle)]">
              {card.name_en}
            </div>
          ) : null}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span
              className={`inline-flex items-center rounded-md border px-2.5 py-1 text-sm font-semibold ${STANCE_BG[card.glance.stance]}`}
            >
              {STANCE_LABEL[card.glance.stance]}
            </span>
            {card.tags?.length
              ? card.tags.slice(0, 5).map((t) => (
                  <span
                    key={t}
                    className="text-xs rounded-md border border-[var(--surface-border)] px-2 py-0.5 text-[var(--surface-text-muted)]"
                  >
                    {t}
                  </span>
                ))
              : null}
          </div>
        </div>

        {/* Right: price + change + asof */}
        <div className="text-left md:text-right shrink-0">
          <div className="text-3xl md:text-[2rem] font-bold tabular-nums leading-tight">
            {mark}
            {card.price.toLocaleString()}
          </div>
          <div className={`text-sm font-semibold tabular-nums ${changeColor}`}>
            {sign}
            {change.toLocaleString()} ({sign}
            {changePct.toFixed(2)}%)
          </div>
          <div
            className="mt-1 text-xs text-[var(--surface-text-subtle)]"
            title={asofRelative}
          >
            {asofAbsolute}
          </div>
        </div>
      </div>
    </header>
  );
}

function _formatRelative(when: Date): string {
  const diffSec = Math.max(0, Math.floor((Date.now() - when.getTime()) / 1000));
  if (diffSec < 60) return "방금 전";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}분 전`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}시간 전`;
  const diffDay = Math.floor(diffHour / 24);
  return `${diffDay}일 전`;
}
