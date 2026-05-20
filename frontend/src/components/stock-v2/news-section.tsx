"use client";

import { Newspaper } from "lucide-react";
import type { NewsItem, PoliticalSignalCard } from "@/types/card";
import { SectionShell } from "./section-shell";

const IMPACT_EMOJI: Record<NewsItem["impact"], string> = {
  positive: "▲",
  negative: "▼",
  mixed: "◆",
  neutral: "○",
};

const IMPACT_COLOR: Record<NewsItem["impact"], string> = {
  positive: "text-red-600 dark:text-red-400",
  negative: "text-blue-600 dark:text-blue-400",
  mixed: "text-amber-600 dark:text-amber-400",
  neutral: "text-[var(--surface-text-muted)]",
};

const IMPACT_LABEL: Record<NewsItem["impact"], string> = {
  positive: "긍정",
  negative: "부정",
  mixed: "양면",
  neutral: "중립",
};

const DIRECTION_BADGE: Record<PoliticalSignalCard["direction"], { label: string; cls: string }> = {
  long: { label: "매수 쪽 영향", cls: "bg-red-500/15 text-red-700 dark:text-red-300 border-red-500/40" },
  short: { label: "매도·회피 영향", cls: "bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-500/40" },
  avoid: { label: "관망", cls: "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/40" },
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

// 2026-05-19 — 시그널 상태 (backend `_fetch_political_signals` 가 분류).
const STATUS_BADGE: Record<
  NonNullable<PoliticalSignalCard["status"]>,
  { label: string; cls: string }
> = {
  new: { label: "신규", cls: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/40" },
  active: { label: "● 진행 중", cls: "bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-500/40" },
  fading: { label: "약화", cls: "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/40" },
  // expired 는 backend 가 기본 fetch 에서 제외하지만 type 완전성 유지.
  expired: { label: "✕ 영향 종료", cls: "bg-[var(--surface-section-hover)] text-[var(--surface-text-muted)] border-[var(--surface-border)]" },
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
      ? `${political.length}건 정치 시그널 · 뉴스 ${news.length}건`
      : news.length === 0
      ? "최근 뉴스 없음"
      : compactNewsText(news);

  return (
    <SectionShell
      icon={<Newspaper size={17} />}
      title="뉴스 / 이슈"
      compact={<span>{compact}</span>}
      expanded={<NewsExpanded news={news} political={political} />}
      helpText={
        <div className="space-y-1.5">
          <p>
            <strong>최근 14일 이 종목 관련 뉴스</strong>. 블로그·SEO 스팸·aggregator
            는 자동 제외하고 <em>정통 매체</em>(한국경제·매일경제·연합뉴스·Bloomberg·Reuters
            등) 만 통과.
          </p>
          <ul className="ml-3 space-y-0.5 list-disc">
            <li><strong>▲ 빨강</strong> = 긍정 영향 · <strong>▼ 파랑</strong> = 부정 · ◆ = 양면 · ○ = 중립</li>
            <li><strong>정치 시그널</strong> — 트럼프 Truth Social 발언이 이 종목에 미치는 영향 (LLM 자동 매핑)</li>
            <li>제목 클릭 시 원문 매체 이동</li>
          </ul>
        </div>
      }
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
            <li
              key={i}
              className="rounded-md border border-[var(--surface-border)] bg-[var(--surface-section-hover)]/35 px-3 py-2.5"
            >
              <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                <span className={`inline-flex items-center gap-1 rounded border border-current/25 px-1.5 py-0.5 text-[10px] font-semibold ${IMPACT_COLOR[n.impact]}`}>
                  {IMPACT_EMOJI[n.impact]} {IMPACT_LABEL[n.impact]}
                </span>
                <span className="text-xs text-[var(--surface-text-muted)]">
                  {n.source} · {new Date(n.published_at).toLocaleDateString("ko-KR")}
                </span>
              </div>
              {n.summary ? (
                <p className="text-sm font-medium leading-relaxed text-[var(--surface-text)]">
                  {n.summary}
                </p>
              ) : null}
              {n.key_quote ? (
                <blockquote className="mt-2 border-l-2 border-[var(--surface-border)] pl-2 text-xs leading-relaxed text-[var(--surface-text-muted)]">
                  {n.key_quote}
                </blockquote>
              ) : null}
              {n.why_it_matters ? (
                <p className="mt-2 text-xs leading-relaxed text-[var(--surface-text-muted)]">
                  <span className="font-semibold text-[var(--surface-text)]">왜 중요: </span>
                  {n.why_it_matters}
                </p>
              ) : null}
              <a
                href={n.url}
                target="_blank"
                rel="noreferrer"
                className="mt-1.5 block text-xs leading-relaxed text-[var(--surface-text-muted)] hover:text-[var(--surface-text)] hover:underline"
              >
                {n.title}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PoliticalBlock({ signals }: { signals: PoliticalSignalCard[] }) {
  return (
    <div className="relative rounded-md border-2 border-amber-500/40 dark:border-amber-500/30 bg-amber-500/5 pl-4 pr-3 py-3 before:absolute before:left-0 before:top-0 before:bottom-0 before:w-[3px] before:bg-amber-500 before:rounded-l-md before:content-['']">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <span className="inline-flex items-center bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30 px-1.5 py-0.5 rounded text-[10px] font-semibold">
          정치 시그널
        </span>
        <span className="text-sm font-semibold text-amber-700 dark:text-amber-300">
          트럼프 Truth Social
        </span>
        <span className="text-xs font-normal text-[var(--surface-text-muted)]">
          · 단기 매매 영향
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
                {s.status ? (
                  <span
                    className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium ${STATUS_BADGE[s.status].cls}`}
                    title={
                      s.days_old != null
                        ? `${s.days_old}일 전 · ${STATUS_BADGE[s.status].label}`
                        : STATUS_BADGE[s.status].label
                    }
                  >
                    {STATUS_BADGE[s.status].label}
                  </span>
                ) : null}
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

function compactNewsText(news: NewsItem[]): string {
  const counts = news.reduce(
    (acc, item) => {
      acc[item.impact] += 1;
      return acc;
    },
    { positive: 0, negative: 0, mixed: 0, neutral: 0 } as Record<NewsItem["impact"], number>,
  );
  const signalParts = [
    counts.positive > 0 ? `긍정 ${counts.positive}` : null,
    counts.negative > 0 ? `부정 ${counts.negative}` : null,
    counts.mixed > 0 ? `양면 ${counts.mixed}` : null,
  ].filter(Boolean);
  const signal = signalParts.length > 0 ? signalParts.join(" / ") : "중립 중심";

  return `관련 뉴스 ${news.length}건 · ${signal} · 펼쳐서 핵심 확인`;
}
