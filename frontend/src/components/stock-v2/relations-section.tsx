"use client";

import type { RelationsSummary } from "@/types/card";
import { SectionShell } from "./section-shell";

const RELATION_LABEL: Record<string, string> = {
  peer: "peer",
  supply_upstream: "공급-상류",
  supply_downstream: "공급-하류",
  group: "그룹",
  theme: "테마",
  macro: "매크로",
};

export function RelationsSection({ relations }: { relations: RelationsSummary }) {
  const count = relations.relations?.length ?? 0;
  return (
    <SectionShell
      emoji="🔗"
      title="관계"
      compact={
        <span>{relations.one_line || (count > 0 ? `${count}개 관계` : "관계 데이터 없음")}</span>
      }
      expanded={<RelationsExpanded relations={relations} />}
    />
  );
}

function RelationsExpanded({ relations }: { relations: RelationsSummary }) {
  const rels = relations.relations ?? [];
  if (rels.length === 0) {
    return <p className="text-sm text-[var(--surface-text-muted)]">등록된 관계 없음</p>;
  }
  return (
    <div className="space-y-3 text-sm">
      <table className="w-full text-xs">
        <thead className="text-[var(--surface-text-muted)]">
          <tr>
            <th className="text-left font-medium pb-1.5">종목 / 테마</th>
            <th className="text-left font-medium pb-1.5">유형</th>
            <th className="text-right font-medium pb-1.5">강도</th>
            <th className="text-right font-medium pb-1.5">변동</th>
          </tr>
        </thead>
        <tbody>
          {rels.slice(0, 10).map((r, i) => {
            const change = r.today_change_pct;
            const changeColor =
              change == null
                ? "text-[var(--surface-text-muted)]"
                : change > 0
                  ? "text-emerald-600 dark:text-emerald-400"
                  : change < 0
                    ? "text-rose-600 dark:text-rose-400"
                    : "text-[var(--surface-text-muted)]";
            return (
              <tr key={i} className="border-t border-[var(--surface-border)]">
                <td className="py-1.5">
                  {r.target_name}
                  {r.target_ticker && r.target_ticker !== r.target_name ? (
                    <span className="ml-1 text-[var(--surface-text-muted)]">
                      ({r.target_ticker})
                    </span>
                  ) : null}
                </td>
                <td className="text-[var(--surface-text-muted)]">
                  {RELATION_LABEL[r.relation_type] ?? r.relation_type}
                </td>
                <td className="text-right tabular-nums">{(r.strength * 100).toFixed(0)}%</td>
                <td className={`text-right tabular-nums ${changeColor}`}>
                  {change != null
                    ? `${change > 0 ? "+" : ""}${change.toFixed(1)}%`
                    : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <a
        href="#"
        onClick={(e) => e.preventDefault()}
        className="inline-block text-xs text-[var(--surface-text-muted)] hover:text-[var(--surface-text)]"
      >
        그래프로 보기 → <span className="text-[var(--surface-text-subtle)]">(P3 예정)</span>
      </a>
    </div>
  );
}
