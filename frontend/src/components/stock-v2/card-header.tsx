"use client";

import type { StockCard } from "@/types/card";

const STANCE_LABEL = {
  BUY: "매수 후보",
  WATCH: "관망",
  REJECT: "보류",
} as const;

const STANCE_BG = {
  BUY: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300",
  WATCH:
    "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300",
  REJECT: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
} as const;

/**
 * Card header — ticker · names · market · tags · stance badge · price · asof.
 * Plan §7.1.
 */
export function CardHeader({ card }: { card: StockCard }) {
  const change = card.change ?? 0;
  const changePct = card.change_pct ?? 0;
  const sign = change > 0 ? "+" : "";
  const changeColor =
    change > 0
      ? "text-green-600 dark:text-green-400"
      : change < 0
        ? "text-red-600 dark:text-red-400"
        : "text-[var(--surface-text-muted)]";
  const currencyMark = card.market === "KR" ? "₩" : card.market === "US" ? "$" : "";

  // asof — show absolute time; tooltip relative time per plan §17.5
  const asofAbsolute = card.asof
    ? new Date(card.asof).toLocaleString("ko-KR", {
        dateStyle: "short",
        timeStyle: "short",
      })
    : "—";
  const asofRelative = card.asof ? _formatRelative(new Date(card.asof)) : "";

  return (
    <header className="border-b border-[var(--surface-border)] p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="text-sm text-[var(--surface-text-muted)]">
            <span className="font-medium text-[var(--surface-text)]">{card.ticker}</span>
            {card.name_ko ? <> · {card.name_ko}</> : null}
            {card.name_en ? <> · {card.name_en}</> : null}
            {card.market ? <> · {card.market}</> : null}
          </div>

          {card.tags?.length ? (
            <div className="mt-1 flex flex-wrap gap-1">
              {card.tags.map((t) => (
                <span
                  key={t}
                  className="text-xs rounded-md border border-[var(--surface-border)] px-2 py-0.5"
                >
                  {t}
                </span>
              ))}
            </div>
          ) : null}

          <div
            className={`mt-2 inline-flex items-center rounded-md px-2 py-1 text-sm font-medium ${STANCE_BG[card.glance.stance]}`}
          >
            {STANCE_LABEL[card.glance.stance]}
          </div>
        </div>

        <div className="text-right shrink-0">
          <div className="text-2xl md:text-3xl font-bold tabular-nums">
            {currencyMark}
            {card.price.toLocaleString()}
          </div>
          <div className={`text-sm font-medium tabular-nums ${changeColor}`}>
            {sign}
            {change.toLocaleString()} ({sign}
            {changePct.toFixed(2)}%)
          </div>
          <div
            className="text-xs text-[var(--surface-text-muted)]"
            title={asofRelative}
          >
            {asofAbsolute}
          </div>
        </div>
      </div>
    </header>
  );
}

/** "2시간 전" / "3분 전" / "방금 전" — relative time in Korean. */
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
