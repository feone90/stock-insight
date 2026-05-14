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

// 2026-05-14 Codex 권고 C: source 증거 강도 기반 ranking. TYPE_PRIORITY
// 같은 타입 안에서 더 강한 증거(SEC/DART filing > news rationale > 큐레이션
// > 웹탐색 > mechanical) 가 위에 오게. 고신뢰 sector peer 가 저신뢰
// contract 위에 오는 역전 방지. project_ontology_codex_review §우선순위 C.
const SOURCE_CLASS_PRIORITY: Record<string, number> = {
  sec_8k: 0,            // SEC 8-K Item 1.01 — 가장 강한 계약 증거
  dart_contract: 0,     // KR 주요사항보고서 (현재 미구현, 미래 동등)
  news: 1,              // news rationale (본문 인용 + URL)
  candidate_promote: 2, // correlation-verified, candidate → live
  curated_relation: 2,  // LLM 종합 큐레이션
  llm_web_search: 3,    // Tavily 웹 탐색
  sector_match: 4,      // mechanical sector pair (backend 에서 카드 제외됨)
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

function isInverseCompetitor(r: Relation): boolean {
  return r.relation_type === "competitor" && r.signal_direction === "inverse";
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
  // Codex 권고 D: inverse competitor(=zero-sum)는 시니어가 가장 먼저 봐야 할
  // 신호. 표 안 ⇄ 배지가 아니라 dedicated callout 으로 표 위에 띄움.
  // 표에서는 제외 — 같은 정보 두 번 노출 방지 (cap 자리 절약).
  const inverseCompetitors = filtered
    .filter(isInverseCompetitor)
    .sort((a, b) => {
      const ca = (a.confidence ?? 0.5) * a.strength;
      const cb = (b.confidence ?? 0.5) * b.strength;
      return cb - ca;
    });
  const restSorted = [...filtered]
    .filter((r) => !isInverseCompetitor(r))
    .sort((a, b) => compareRelations(a, b, selfIsKR));
  if (inverseCompetitors.length === 0 && restSorted.length === 0) {
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
      {inverseCompetitors.length > 0 ? (
        <InverseCallout inverses={inverseCompetitors} />
      ) : null}
      {restSorted.length > 0 ? (
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
            {restSorted.slice(0, CAP).map((r, i) => (
              <RelationRow key={`${r.target_ticker}-${r.relation_type}-${r.source ?? i}`} rel={r} />
            ))}
          </tbody>
        </table>
      ) : null}
      {restSorted.length > CAP ? (
        <p className="text-xs text-[var(--surface-text-subtle)]">
          + 핵심 관계 {restSorted.length - CAP}개 더 + 동종업계/그룹/테마 등 부가
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

/**
 * Zero-sum (inverse competitor) dedicated callout.
 *
 * 2026-05-14 Codex 시니어 트레이더 권고 D: "한쪽이 이기면 다른 쪽이 진다"
 * 식 신호는 매매 판단에서 가장 먼저 보는 정보. 표 안 ⇄ 배지로는 묻힘 —
 * 표 위에 큰 박스로 띄워 시니어가 첫 줄에서 잡도록.
 *
 * 카피 가이드(memory: feedback_card_user_facing_copy): 약어 X, 비유 자연어.
 */
function InverseCallout({ inverses }: { inverses: Relation[] }) {
  const TOP = 3;
  return (
    <div className="relative rounded-md border-2 border-blue-500/40 dark:border-blue-500/30 bg-blue-500/5 pl-4 pr-3 py-3 before:absolute before:left-0 before:top-0 before:bottom-0 before:w-[3px] before:bg-blue-500 before:rounded-l-md before:content-['']">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <span className="inline-flex items-center bg-blue-500/15 text-blue-700 dark:text-blue-300 border border-blue-500/30 px-1.5 py-0.5 rounded text-[10px] font-semibold">
          zero-sum 신호
        </span>
        <span className="text-sm font-semibold text-blue-700 dark:text-blue-300">
          ⇄ 한쪽이 이기면 다른 쪽이 진다
        </span>
      </div>
      <ul className="space-y-2">
        {inverses.slice(0, TOP).map((r, i) => {
          const conf = Math.round((r.confidence ?? 0.5) * 100);
          const sourceLabel = r.source ? SOURCE_LABEL[r.source] ?? r.source : null;
          return (
            <li key={`${r.target_ticker}-${i}`} className="text-sm">
              <div className="flex flex-wrap items-baseline gap-1.5">
                <span className="font-medium">{r.target_name}</span>
                {r.target_ticker && r.target_ticker !== r.target_name ? (
                  <span className="text-xs text-[var(--surface-text-muted)]">
                    ({r.target_ticker})
                  </span>
                ) : null}
                <span className="text-xs text-[var(--surface-text-subtle)]">
                  · 신뢰 {conf}%
                  {sourceLabel ? ` · 출처 ${sourceLabel}` : ""}
                </span>
              </div>
              {r.rationale ? (
                <p className="mt-0.5 text-xs text-[var(--surface-text-muted)] leading-snug">
                  {r.rationale}
                </p>
              ) : (
                <p className="mt-0.5 text-xs text-[var(--surface-text-subtle)] italic">
                  같은 시장에서 직접 경쟁 — 점유율 이동에 반대로 반응
                </p>
              )}
              {r.source_url ? (
                <a
                  href={r.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[11px] text-blue-600 dark:text-blue-400 hover:underline"
                >
                  원문 보기 ↗
                </a>
              ) : null}
            </li>
          );
        })}
      </ul>
      {inverses.length > TOP ? (
        <p className="mt-2 text-[11px] text-[var(--surface-text-subtle)]">
          + zero-sum 경쟁자 {inverses.length - TOP}명 더 — 그래프에서 전체 보기
        </p>
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

function sourceClass(source: string | undefined): number {
  if (!source) return 9;
  return SOURCE_CLASS_PRIORITY[source] ?? 9;
}

function compareRelations(a: Relation, b: Relation, selfIsKR: boolean | null): number {
  // 1차: 관계 유형 priority (contract → competitor → complementary → supply → regulatory).
  const pa = TYPE_PRIORITY[a.relation_type] ?? 9;
  const pb = TYPE_PRIORITY[b.relation_type] ?? 9;
  if (pa !== pb) return pa - pb;
  // 2차: 증거 강도 (filing > news rationale > curation > web search). 같은
  // 유형이면 강한 증거가 위. high-conf mechanical 이 low-conf contract 위에
  // 가는 역전 방지.
  const sca = sourceClass(a.source);
  const scb = sourceClass(b.source);
  if (sca !== scb) return sca - scb;
  // 3차: 다른 시장 우선 — KR 카드에 US peer (vice versa) 노출 보장.
  if (selfIsKR !== null) {
    const aCross = isKRTicker(a.target_ticker) !== selfIsKR;
    const bCross = isKRTicker(b.target_ticker) !== selfIsKR;
    if (aCross !== bCross) return aCross ? -1 : 1;
  }
  // 4차: confidence × strength desc.
  const sa = (a.confidence ?? 0.5) * a.strength;
  const sb = (b.confidence ?? 0.5) * b.strength;
  return sb - sa;
}
