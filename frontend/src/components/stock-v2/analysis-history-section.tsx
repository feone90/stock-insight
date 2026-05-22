"use client";

import { Archive, Clock3, Newspaper, TrendingDown, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getAnalysisHistory } from "@/services/api";
import type { AnalysisHistoryItem, EventDirection, Stance } from "@/types/card";
import { SectionShell } from "./section-shell";

const STANCE_LABEL: Record<Stance, string> = {
  BUY: "매수 후보",
  WATCH: "관찰",
  REJECT: "보류",
};

const IMPACT_CLASS: Record<EventDirection, string> = {
  positive: "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300",
  negative: "border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-300",
  mixed: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  neutral: "border-[var(--surface-border)] bg-[var(--surface-card)] text-[var(--surface-text-muted)]",
};

export function AnalysisHistorySection({ ticker }: { ticker: string }) {
  const [items, setItems] = useState<AnalysisHistoryItem[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getAnalysisHistory(ticker, 14)
      .then((res) => {
        if (!cancelled) {
          setItems(res.items);
          setLoaded(true);
        }
      })
      .catch(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const carryForward = useMemo(() => findCarryForward(items), [items]);
  const compact = !loaded
    ? "이전 분석 불러오는 중"
    : items.length <= 1
      ? "아직 쌓인 이전 분석 없음"
      : `최근 daily 분석 ${items.length}건 · 판단 흐름 확인`;

  return (
    <SectionShell
      icon={<Archive size={17} />}
      title="분석 히스토리"
      compact={compact}
      defaultOpen={false}
      helpText="매일 새 카드가 만들어져도 이전 판단 근거를 잃지 않도록, 과거 daily 분석의 핵심 의견·뉴스·가격 원인을 종목 기억으로 보여줍니다."
      expanded={
        <div className="space-y-3">
          {carryForward ? (
            <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
              새 뉴스가 없을 때도 직전 핵심 근거는 유지됩니다: {carryForward}
            </div>
          ) : null}
          {items.length === 0 ? (
            <div className="rounded-md border border-dashed border-[var(--surface-border)] px-3 py-3 text-sm text-[var(--surface-text-muted)]">
              아직 저장된 daily 분석이 없습니다. 분석이 며칠 쌓이면 판단 변화가 여기에 남습니다.
            </div>
          ) : (
            <ol className="space-y-2">
              {items.map((item, index) => (
                <HistoryRow key={`${item.date}-${index}`} item={item} isLatest={index === 0} />
              ))}
            </ol>
          )}
        </div>
      }
    />
  );
}

function HistoryRow({ item, isLatest }: { item: AnalysisHistoryItem; isLatest: boolean }) {
  const stance = item.stance ? STANCE_LABEL[item.stance] : "판단 없음";
  return (
    <li className="rounded-md border border-[var(--surface-border)] bg-[var(--surface-card)] px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="inline-flex items-center gap-1 text-[var(--surface-text-muted)]">
          <Clock3 size={13} />
          {formatDate(item.date)}
        </span>
        {isLatest ? (
          <span className="rounded border border-blue-500/30 bg-blue-500/10 px-1.5 py-0.5 text-[10px] text-blue-700 dark:text-blue-300">
            최신
          </span>
        ) : null}
        <span className="rounded border border-[var(--surface-border)] px-1.5 py-0.5 text-[10px] text-[var(--surface-text-muted)]">
          {item.final_grade || "-"} · {stance}
        </span>
        <span className="inline-flex items-center gap-1 text-[10px] text-[var(--surface-text-subtle)]">
          <Newspaper size={12} />
          뉴스 {item.news_count}건
        </span>
      </div>
      <div className="mt-1.5 text-sm font-medium text-[var(--surface-text)]">
        {item.one_line}
      </div>
      {item.price_move ? (
        <div className="mt-1 inline-flex items-center gap-1 text-xs text-[var(--surface-text-muted)]">
          {item.price_move.includes("-") ? <TrendingDown size={13} /> : <TrendingUp size={13} />}
          {item.price_move}
        </div>
      ) : null}
      {item.key_news.length > 0 ? (
        <div className="mt-2 flex gap-1.5 overflow-x-auto pb-1">
          {item.key_news.map((news) => (
            <a
              key={`${news.title}-${news.published_at || ""}`}
              href={news.url || undefined}
              target={news.url ? "_blank" : undefined}
              rel={news.url ? "noreferrer" : undefined}
              className={`min-w-[170px] rounded border px-2 py-1.5 ${IMPACT_CLASS[news.impact]}`}
              title={news.summary}
            >
              <div className="truncate text-[11px] font-medium">{news.title}</div>
              <div className="mt-0.5 line-clamp-2 text-[10px] opacity-85">{news.summary}</div>
            </a>
          ))}
        </div>
      ) : null}
    </li>
  );
}

function findCarryForward(items: AnalysisHistoryItem[]): string | null {
  const latest = items[0];
  if (!latest || latest.news_count > 0) return null;
  const previous = items.slice(1).find((item) => item.price_move || item.key_news.length > 0);
  if (!previous) return null;
  return previous.price_move || previous.key_news[0]?.summary || null;
}

function formatDate(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return `${d.getMonth() + 1}월 ${d.getDate()}일`;
}
