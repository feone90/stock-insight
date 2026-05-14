"use client";

import type { Relation, RelationType, RelationsSummary, SignalDirection } from "@/types/card";
import { SectionShell } from "./section-shell";

// 가족 친화 자연어 라벨 — 약어 / 영어 노출 X (feedback_card_user_facing_copy).
const RELATION_LABEL: Record<RelationType, string> = {
  peer: "동종업계",
  supply_upstream: "공급망 (상류)",
  supply_downstream: "공급망 (하류)",
  group: "그룹사",
  theme: "테마",
  macro: "매크로",
  competitor: "경쟁",
  contract_supplier: "공급 계약",
  contract_customer: "구매 계약",
  complementary: "상호 보완",
  regulatory_link: "규제 연동",
};

// 2026-05-14 Codex 권고: 카드는 시니어 매매 의사결정용 — actionable type
// 만 노출. peer / group / theme / macro 는 graph 전용 (sector context 정도).
// project_ontology_codex_review_2026_05_14 메모 §우선순위 A/B/E.
const CARD_ACTIONABLE_TYPES: ReadonlySet<RelationType> = new Set([
  "contract_supplier",
  "contract_customer",
  "competitor",
  "complementary",
  "supply_upstream",
  "supply_downstream",
  "regulatory_link",
]);

// Highest information density first — discovery-driven types beat plain peer.
const TYPE_PRIORITY: Record<RelationType, number> = {
  contract_supplier: 0,
  contract_customer: 0,
  competitor: 1,
  complementary: 2,
  supply_upstream: 3,
  supply_downstream: 3,
  regulatory_link: 4,
  group: 5,
  theme: 6,
  macro: 7,
  peer: 8,
};

const SOURCE_LABEL: Record<string, string> = {
  sector_match: "섹터매칭",
  sec_8k: "SEC 8-K",
  dart_contract: "DART 공시",
  news: "뉴스",
  curated_relation: "AI 큐레이션",
  candidate_promote: "후보 승격",
  llm_web_search: "웹 탐색",
};

export function RelationsSection({
  relations,
  ticker,
}: {
  relations: RelationsSummary;
  ticker?: string;
}) {
  const count = relations.relations?.length ?? 0;
  const summary = summariseRelations(relations.relations ?? []);
  return (
    <SectionShell
      emoji="🔗"
      title="관계"
      compact={
        <span>
          {relations.one_line || (count > 0 ? summary : "관계 데이터 없음")}
        </span>
      }
      expanded={<RelationsExpanded relations={relations} selfTicker={ticker} />}
    />
  );
}

function summariseRelations(rels: Relation[]): string {
  // compact 라인은 actionable 관계만 카운트 — peer/group/theme/macro 는 graph 전용.
  const actionable = rels.filter((r) => CARD_ACTIONABLE_TYPES.has(r.relation_type));
  if (actionable.length === 0) return "핵심 관계 없음";
  const counts: Partial<Record<RelationType, number>> = {};
  for (const r of actionable) counts[r.relation_type] = (counts[r.relation_type] ?? 0) + 1;
  const parts: string[] = [];
  for (const t of Object.keys(counts) as RelationType[]) {
    parts.push(`${RELATION_LABEL[t] ?? t} ${counts[t]}`);
  }
  return `${actionable.length}개 · ${parts.join(", ")}`;
}

function RelationsExpanded({
  relations,
  selfTicker,
}: {
  relations: RelationsSummary;
  selfTicker?: string;
}) {
  const selfIsKR = selfTicker ? isKRTicker(selfTicker) : null;
  // Codex 권고 A+B: 카드는 actionable type 만 + cap 24 → 6 (인지 한계).
  // mechanical sector peer 양적 압도로 진짜 신호 묻히던 패턴 fix.
  // 전체 관계망은 "Ontology 그래프 →" 링크에서 확인.
  const filtered = (relations.relations ?? []).filter((r) =>
    CARD_ACTIONABLE_TYPES.has(r.relation_type),
  );
  const sorted = [...filtered].sort((a, b) =>
    compareRelations(a, b, selfIsKR),
  );
  if (sorted.length === 0) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-[var(--surface-text-muted)]">
          핵심 관계 없음 — 계약·경쟁·공급망·규제 같은 의사결정 가능한 신호
          아직 추출되지 않음
        </p>
        {selfTicker ? (
          <a
            href={`/stock/${selfTicker}/graph`}
            className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline"
          >
            그래프에서 전체 관계망 보기 →
          </a>
        ) : null}
      </div>
    );
  }
  const CAP = 6;
  return (
    <div className="space-y-3 text-sm">
      <table className="w-full text-xs">
        <thead className="text-[var(--surface-text-muted)]">
          <tr>
            <th className="text-left font-medium pb-1.5">종목 / 테마</th>
            <th className="text-left font-medium pb-1.5">유형</th>
            <th className="text-left font-medium pb-1.5">방향</th>
            <th className="text-right font-medium pb-1.5">강도</th>
            <th className="text-right font-medium pb-1.5">신뢰</th>
            <th className="text-right font-medium pb-1.5">변동</th>
            <th className="text-left font-medium pb-1.5 pl-2">출처</th>
          </tr>
        </thead>
        <tbody>
          {sorted.slice(0, CAP).map((r, i) => (
            <RelationRow key={`${r.target_ticker}-${r.relation_type}-${r.source ?? i}`} rel={r} />
          ))}
        </tbody>
      </table>
      {sorted.length > CAP ? (
        <p className="text-xs text-[var(--surface-text-subtle)]">
          + 핵심 관계 {sorted.length - CAP}개 더 + 동종업계/그룹/테마 등 부가
          관계 — 그래프에서 전체 보기
        </p>
      ) : (
        <p className="text-xs text-[var(--surface-text-subtle)]">
          동종업계·그룹·테마 같은 부가 관계는 그래프에서만 표시
        </p>
      )}
      {selfTicker ? (
        <a
          href={`/stock/${selfTicker}/graph`}
          className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline"
        >
          Ontology 그래프 →
        </a>
      ) : null}
    </div>
  );
}

function isKRTicker(ticker: string): boolean {
  return /^\d{6}$/.test(ticker);
}

function RelationRow({ rel }: { rel: Relation }) {
  const change = rel.today_change_pct;
  const changeColor =
    change == null
      ? "text-[var(--surface-text-muted)]"
      : change > 0
        ? "text-red-600 dark:text-red-400"
        : change < 0
          ? "text-blue-600 dark:text-blue-400"
          : "text-[var(--surface-text-muted)]";

  const confidence = rel.confidence ?? 0.5;
  const conf = Math.round(confidence * 100);
  const sourceLabel = rel.source ? SOURCE_LABEL[rel.source] ?? rel.source : null;

  const rationale = rel.rationale?.trim() || null;

  return (
    <>
      <tr
        className="border-t border-[var(--surface-border)]"
        title={rationale ?? undefined}
      >
        <td className="py-1.5">
          {rel.target_name}
          {rel.target_ticker && rel.target_ticker !== rel.target_name ? (
            <span className="ml-1 text-[var(--surface-text-muted)]">({rel.target_ticker})</span>
          ) : null}
        </td>
        <td className="text-[var(--surface-text-muted)]">
          {RELATION_LABEL[rel.relation_type] ?? rel.relation_type}
        </td>
        <td>
          <SignalBadge direction={rel.signal_direction} />
        </td>
        <td className="text-right tabular-nums">{(rel.strength * 100).toFixed(0)}%</td>
        <td className="text-right tabular-nums text-[var(--surface-text-muted)]">{conf}%</td>
        <td className={`text-right tabular-nums ${changeColor}`}>
          {change != null ? `${change > 0 ? "+" : ""}${change.toFixed(1)}%` : "—"}
        </td>
        <td className="pl-2 text-xs">
          {rel.source_url ? (
            <a
              href={rel.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 dark:text-blue-400 hover:underline"
              title={sourceLabel ?? rel.source ?? "source"}
            >
              {sourceLabel ?? "원문"} ↗
            </a>
          ) : (
            <span className="text-[var(--surface-text-subtle)]">{sourceLabel ?? "—"}</span>
          )}
        </td>
      </tr>
      {rationale ? (
        <tr className="border-t border-[var(--surface-border)]/40">
          <td
            colSpan={7}
            className="pb-2 pl-2 text-[11px] italic leading-snug text-[var(--surface-text-subtle)]"
          >
            <span className="not-italic mr-1 text-[var(--surface-text-muted)]">근거:</span>
            {rationale}
          </td>
        </tr>
      ) : null}
    </>
  );
}

function SignalBadge({ direction }: { direction?: SignalDirection }) {
  if (direction === "inverse") {
    return <span className="text-blue-600 dark:text-blue-400" title="역(zero-sum) 신호">⇄</span>;
  }
  if (direction === "negative") {
    return <span className="text-amber-600 dark:text-amber-400" title="부정 신호">↓</span>;
  }
  return <span className="text-red-600 dark:text-red-400" title="긍정 신호">↑</span>;
}

function compareRelations(a: Relation, b: Relation, selfIsKR: boolean | null): number {
  const pa = TYPE_PRIORITY[a.relation_type] ?? 9;
  const pb = TYPE_PRIORITY[b.relation_type] ?? 9;
  if (pa !== pb) return pa - pb;
  // Cross-market peer first: KR card surfaces US peers (and vice versa) before
  // same-market — otherwise ticker ASC pushes the other side off the cap window.
  if (selfIsKR !== null) {
    const aCross = isKRTicker(a.target_ticker) !== selfIsKR;
    const bCross = isKRTicker(b.target_ticker) !== selfIsKR;
    if (aCross !== bCross) return aCross ? -1 : 1;
  }
  // Final tie-break: confidence × strength desc.
  const sa = (a.confidence ?? 0.5) * a.strength;
  const sb = (b.confidence ?? 0.5) * b.strength;
  return sb - sa;
}
