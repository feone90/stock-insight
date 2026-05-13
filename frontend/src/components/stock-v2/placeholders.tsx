"use client";

import { useState } from "react";
import type { Citation, SourceType } from "@/types/card";

/**
 * Card footer — citation pool drilldown.
 *
 * Codex review v2 [high]: 이전 placeholder ("출처 추적은 sub-phase F 예정")
 * 자리를 진짜 출처 풀로 교체. 카드 안에서 어떤 결론 (stance / supports /
 * decision) 옆에 [N] 배지가 떠도, 그 N 의 전체 메타 (label / url / timestamp)
 * 를 한 번에 펼쳐 검증할 수 있어야 자본 운용 도구로서 신뢰가 선다.
 */

const SOURCE_LABEL: Record<SourceType, string> = {
  db: "DB",
  market_data: "시세",
  news: "뉴스",
  disclosure: "공시",
  web: "웹",
  curated_relation: "AI 큐레이션",
};

export function CardFooter({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState(false);
  const total = citations.length;

  return (
    <footer className="border-t border-[var(--surface-border)] px-5 py-4 text-sm text-[var(--surface-text-muted)]">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center justify-between w-full text-left hover:text-[var(--surface-text)] transition-colors"
        aria-expanded={open}
      >
        <span>
          출처 풀 · 총 <span className="font-semibold text-[var(--surface-text)] tabular-nums">{total}</span> 건
          <span className="ml-2 text-xs text-[var(--surface-text-subtle)]">
            (카드 본문의 [N] 배지가 여기 id 를 가리킵니다)
          </span>
        </span>
        <span className="text-xs text-[var(--surface-text-subtle)]">
          {open ? "접기 ▲" : "전체 보기 ▼"}
        </span>
      </button>

      {open ? (
        <ul className="mt-3 space-y-1 text-xs">
          {citations.map((c) => (
            <li key={c.id} className="flex items-start gap-2">
              <span className="inline-flex items-center justify-center min-w-[1.6rem] h-[1.2rem] px-1 rounded border border-[var(--surface-border)] bg-[var(--surface-section)] text-[10px] font-mono tabular-nums shrink-0">
                {c.id}
              </span>
              <span className="text-[var(--surface-text-muted)] shrink-0">
                {SOURCE_LABEL[c.source_type] ?? c.source_type}
              </span>
              <span className="text-[var(--surface-text)] flex-1 min-w-0 truncate" title={c.label}>
                {c.label}
              </span>
              {c.timestamp ? (
                <span className="text-[var(--surface-text-subtle)] tabular-nums shrink-0">
                  {c.timestamp}
                </span>
              ) : null}
              {c.url ? (
                <a
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 dark:text-blue-400 hover:underline shrink-0"
                >
                  원문 ↗
                </a>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </footer>
  );
}
