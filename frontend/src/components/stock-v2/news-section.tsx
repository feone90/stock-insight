"use client";

import type { NewsItem } from "@/types/card";
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

export function NewsSection({ news }: { news: NewsItem[] }) {
  const compact =
    news.length === 0
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
      expanded={<NewsExpanded news={news} />}
    />
  );
}

function NewsExpanded({ news }: { news: NewsItem[] }) {
  if (news.length === 0) {
    return <p className="text-sm text-[var(--surface-text-muted)]">최근 뉴스 없음</p>;
  }
  return (
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
  );
}

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n)}…` : s;
}
