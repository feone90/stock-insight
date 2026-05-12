"use client";

import type { NewsItem, PoliticalSignalCard } from "@/types/card";
import { SectionShell } from "./section-shell";

const IMPACT_EMOJI: Record<NewsItem["impact"], string> = {
  positive: "▲",
  negative: "▼",
  mixed: "◆",
  neutral: "○",
};

const IMPACT_COLOR: Record<NewsItem["impact"], string> = {
  positive: "text-emerald-600 dark:text-emerald-400",
  negative: "text-rose-600 dark:text-rose-400",
  mixed: "text-amber-600 dark:text-amber-400",
  neutral: "text-[var(--surface-text-muted)]",
};

const DIRECTION_BADGE: Record<PoliticalSignalCard["direction"], { label: string; cls: string }> = {
  long: { label: "📈 매수 시그널", cls: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/40" },
  short: { label: "📉 매도/회피 시그널", cls: "bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/40" },
  avoid: { label: "⏸ 관망", cls: "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/40" },
};

const STRENGTH_LABEL: Record<PoliticalSignalCard["strength"], string> = {
  high: "강한 영향",
  medium: "중간 영향",
  low: "약한 영향",
};

const WINDOW_LABEL: Record<PoliticalSignalCard["expected_window"], string> = {
  minutes: "수 분 안",
  hours: "수 시간 안",
  "1-3days": "1~3일",
  "1-2weeks": "1~2주",
};

export function NewsSection({
  news,
  political = [],
}: {
  news: NewsItem[];
  political?: PoliticalSignalCard[];
}) {
  const compact =
    political.length > 0
      ? `🇺🇸 ${political.length}건 정치 시그널 · 뉴스 ${news.length}건`
      : news.length === 0
      ? "최근 뉴스 없음"
      : news
          .slice(0, 3)
          .map((n) => `${IMPACT_EMOJI[n.impact]} ${truncate(n.title, 16)}`)
          .join(" · ");

  return (
    <SectionShell
      emoji="📰"
      title="뉴스 / 이슈"
      compact={<span>{compact}</span>}
      expanded={<NewsExpanded news={news} political={political} />}
    />
  );
}

function NewsExpanded({
  news,
  political,
}: {
  news: NewsItem[];
  political: PoliticalSignalCard[];
}) {
  return (
    <div className="space-y-4">
      {political.length > 0 && <PoliticalBlock signals={political} />}
      {news.length === 0 ? (
        <p className="text-sm text-[var(--surface-text-muted)]">최근 뉴스 없음</p>
      ) : (
        <ul className="space-y-2.5 text-sm">
          {news.slice(0, 10).map((n, i) => (
            <li key={i} className="flex gap-2">
              <span className={`shrink-0 mt-0.5 ${IMPACT_COLOR[n.impact]}`}>
                {IMPACT_EMOJI[n.impact]}
              </span>
              <div className="min-w-0 flex-1">
                <a
                  href={n.url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium hover:underline line-clamp-1"
                >
                  {n.title}
                </a>
                <div className="text-xs text-[var(--surface-text-muted)]">
                  {n.source} · {new Date(n.published_at).toLocaleDateString("ko-KR")}
                </div>
                {n.summary ? (
                  <p className="mt-1 text-xs text-[var(--surface-text-muted)] line-clamp-2">
                    {n.summary}
                  </p>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PoliticalBlock({ signals }: { signals: PoliticalSignalCard[] }) {
  return (
    <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3">
      <div className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-amber-700 dark:text-amber-300">
        <span>🇺🇸</span>
        <span>정치 시그널 (트럼프 Truth Social)</span>
        <span className="text-xs font-normal text-[var(--surface-text-muted)]">
          · 자동매매 trigger 기준
        </span>
      </div>
      <ul className="space-y-3">
        {signals.slice(0, 5).map((s, i) => {
          const badge = DIRECTION_BADGE[s.direction];
          return (
            <li key={i} className="text-sm">
              <div className="flex flex-wrap items-center gap-1.5 mb-1">
                <span
                  className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-xs font-medium ${badge.cls}`}
                >
                  {badge.label}
                </span>
                <span className="text-xs text-[var(--surface-text-muted)]">
                  {STRENGTH_LABEL[s.strength]} · {WINDOW_LABEL[s.expected_window]} 안 반응
                </span>
                <span className="text-xs text-[var(--surface-text-muted)]">
                  · 신뢰도 {Math.round(s.confidence * 100)}%
                </span>
              </div>
              <p className="font-medium line-clamp-2">{s.summary_ko}</p>
              <p className="mt-1 text-xs text-[var(--surface-text-muted)] line-clamp-3">
                {s.reasoning}
              </p>
              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-[var(--surface-text-muted)]">
                <span>{new Date(s.posted_at).toLocaleDateString("ko-KR")}</span>
                {s.macro_themes.length > 0 && (
                  <span>· {s.macro_themes.join(" / ")}</span>
                )}
                {s.url && (
                  <>
                    <span>·</span>
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-amber-700 dark:text-amber-300 hover:underline"
                    >
                      원문 보기 ↗
                    </a>
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n)}…` : s;
}
