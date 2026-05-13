"use client";

import type { Citation, SourceType } from "@/types/card";

/**
 * Inline citation drilldown — Codex review v2 [high].
 *
 * 카드의 "왜 BUY?" / 매수/매도/관망 stance / supports / opposes / scenarios /
 * decision 옆에 작은 `[N]` 배지를 붙여 사용자가 hover 로 출처 미리보기,
 * 클릭으로 원문 URL 로 이동할 수 있게 한다. 이전 placeholder 푸터 ("출처 추적은
 * future work") 를 대체.
 *
 * 의사결정 도구 신뢰성의 핵심: stance 가 unaudited claim 으로 떠도는 게 아니라
 * 각 결론이 어느 data 또는 interp citation 에서 나왔는지 즉시 확인 가능.
 */

const SOURCE_BADGE_COLOR: Record<SourceType, string> = {
  db: "bg-slate-500/20 text-slate-200 border-slate-500/40",
  market_data: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  news: "bg-red-500/15 text-red-300 border-red-500/40",
  disclosure: "bg-blue-500/15 text-blue-300 border-blue-500/40",
  web: "bg-purple-500/15 text-purple-300 border-purple-500/40",
  curated_relation: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
};

const SOURCE_LABEL: Record<SourceType, string> = {
  db: "DB",
  market_data: "시세",
  news: "뉴스",
  disclosure: "공시",
  web: "웹",
  curated_relation: "AI 큐레이션",
};

export function CitationBadge({
  id,
  citations,
}: {
  id: number;
  citations: Citation[];
}) {
  const c = citations.find((x) => x.id === id);
  if (!c) {
    // pool 에 없는 id — backend resolve 가 drop 했어야 하나 방어용.
    return null;
  }
  const tooltip = [
    `[${id}] ${SOURCE_LABEL[c.source_type] ?? c.source_type}`,
    c.label,
    c.timestamp ? `시점: ${c.timestamp}` : null,
    c.url ? "클릭 → 원문" : null,
  ]
    .filter(Boolean)
    .join("\n");
  const badge = (
    <span
      className={`mx-0.5 inline-flex items-center justify-center min-w-[1.4rem] px-1 h-[1.1rem] rounded border align-middle text-[10px] font-medium tabular-nums ${
        SOURCE_BADGE_COLOR[c.source_type] ?? SOURCE_BADGE_COLOR.db
      }`}
    >
      {id}
    </span>
  );
  if (c.url) {
    return (
      <a
        href={c.url}
        target="_blank"
        rel="noopener noreferrer"
        title={tooltip}
        className="hover:opacity-80 transition-opacity"
      >
        {badge}
      </a>
    );
  }
  return <span title={tooltip}>{badge}</span>;
}

export function CitationList({
  ids,
  citations,
  className = "",
}: {
  ids: number[];
  citations: Citation[];
  className?: string;
}) {
  if (!ids?.length) return null;
  return (
    <span className={`inline-flex flex-wrap gap-0.5 align-middle ${className}`}>
      {ids.map((id) => (
        <CitationBadge key={id} id={id} citations={citations} />
      ))}
    </span>
  );
}
