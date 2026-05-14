"use client";

import type {
  Relation,
  RelationType,
  RelationsSummary,
  SignalDirection,
} from "@/types/card";
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

const SOURCE_LABEL: Record<string, string> = {
  sector_match: "섹터매칭",
  sec_8k: "SEC 8-K",
  sec_10k_risk: "SEC 10-K Risk",
  dart_contract: "DART 공시",
  news: "뉴스",
  curated_relation: "AI 큐레이션",
  candidate_promote: "후보 승격",
  llm_web_search: "웹 탐색",
};

// 2026-05-14: 양적 축소(cap 24→6) 가 아닌 3-tier 시각 차별 — 정보 손실 0,
// 의미 가시성 ↑. core / business / context 3층으로 분류 후 각 그룹마다 다른
// visual weight (글씨 굵기 / 배경 / 압축도). project_ontology_codex_review §사용자 정정.
type Tier = "core" | "business" | "context";

const CONTEXT_TYPES: ReadonlySet<RelationType> = new Set([
  "peer",
  "group",
  "theme",
  "macro",
]);

function classifyTier(r: Relation): Tier {
  // context: 동종업계 / 그룹 / 테마 / 매크로 또는 mechanical source(sector_match).
  // 정보로는 의미 있지만 매매 의사결정 baseline 아님 → 시각 압축.
  if (CONTEXT_TYPES.has(r.relation_type) || r.source === "sector_match") {
    return "context";
  }
  // core: filing 증거 또는 고신뢰 news rationale. 카드 첫 줄에 시니어가 봐야 할 신호.
  const conf = r.confidence ?? 0.5;
  if (
    r.source === "sec_8k" ||
    r.source === "sec_10k_risk" ||
    r.source === "dart_contract" ||
    conf >= 0.8
  ) {
    return "core";
  }
  return "business";
}

const SOURCE_CLASS_PRIORITY: Record<string, number> = {
  sec_8k: 0,
  dart_contract: 0,
  sec_10k_risk: 0,
  news: 1,
  candidate_promote: 2,
  curated_relation: 2,
  llm_web_search: 3,
  sector_match: 4,
};

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

export function RelationsSection({
  relations,
  ticker,
}: {
  relations: RelationsSummary;
  ticker?: string;
}) {
  // Compact 는 우리 정량 summary 만 — one_line LLM narrative 는 길이 변수라
  // collapsed view 한 줄에서 ellipsis 로 잘림. narrative 는 expanded 상단으로.
  const summary = summariseRelations(relations.relations ?? []);
  return (
    <SectionShell
      emoji="🔗"
      title="관계"
      compact={<span>{summary || "관계 데이터 없음"}</span>}
      expanded={<RelationsExpanded relations={relations} selfTicker={ticker} />}
    />
  );
}

function summariseRelations(rels: Relation[]): string {
  if (rels.length === 0) return "관계 데이터 없음";
  let core = 0;
  let business = 0;
  let context = 0;
  let inverse = 0;
  for (const r of rels) {
    if (isInverseCompetitor(r)) {
      inverse += 1;
      continue;
    }
    const tier = classifyTier(r);
    if (tier === "core") core += 1;
    else if (tier === "business") business += 1;
    else context += 1;
  }
  const parts: string[] = [];
  if (inverse > 0) parts.push(`zero-sum ${inverse}`);
  if (core > 0) parts.push(`핵심 ${core}`);
  if (business > 0) parts.push(`사업 ${business}`);
  if (context > 0) parts.push(`컨텍스트 ${context}`);
  return parts.join(" · ");
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
  const all = relations.relations ?? [];

  // zero-sum competitor 는 표 위 dedicated callout 으로 빠짐 (Codex D).
  const inverseCompetitors = all
    .filter(isInverseCompetitor)
    .sort((a, b) => {
      const ca = (a.confidence ?? 0.5) * a.strength;
      const cb = (b.confidence ?? 0.5) * b.strength;
      return cb - ca;
    });

  // 나머지를 3-tier 분류.
  const rest = all.filter((r) => !isInverseCompetitor(r));
  const cmp = (a: Relation, b: Relation) => compareRelations(a, b, selfIsKR);
  const core = rest.filter((r) => classifyTier(r) === "core").sort(cmp);
  const business = rest.filter((r) => classifyTier(r) === "business").sort(cmp);
  const context = rest.filter((r) => classifyTier(r) === "context").sort(cmp);

  if (all.length === 0) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-[var(--surface-text-muted)]">
          관계 데이터 없음
        </p>
        {selfTicker ? (
          <GraphLink ticker={selfTicker} />
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-3 text-sm">
      {relations.one_line ? (
        <p className="text-xs text-[var(--surface-text-muted)] leading-relaxed">
          {relations.one_line}
        </p>
      ) : null}

      {inverseCompetitors.length > 0 ? (
        <InverseCallout inverses={inverseCompetitors} />
      ) : null}

      {core.length === 0 && business.length === 0 && context.length > 0 ? (
        <p className="text-xs text-[var(--surface-text-muted)] leading-snug">
          사업 본질 관계(계약·경쟁·공급망) 추출 부족 — 회계감리·거래정지·신규
          상장 등 공시·뉴스 정보 부족 종목에서 흔함. 동종업계만 표시.
        </p>
      ) : null}

      {core.length > 0 ? (
        <TierBlock
          tier="core"
          title="🔑 핵심 신호"
          subtitle="filing 증거 또는 신뢰도 80%+ — 의사결정 직결"
          rels={core}
        />
      ) : null}
      {business.length > 0 ? (
        <TierBlock
          tier="business"
          title="📝 사업 관계"
          subtitle="기사·공시에 명시된 supplier·customer·competitor"
          rels={business}
        />
      ) : null}
      {context.length > 0 ? (
        <ContextChips rels={context} />
      ) : null}

      {selfTicker ? <GraphLink ticker={selfTicker} /> : null}
    </div>
  );
}

function GraphLink({ ticker }: { ticker: string }) {
  return (
    <a
      href={`/stock/${ticker}/graph`}
      className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline"
    >
      Ontology 그래프 — 전체 관계망 →
    </a>
  );
}

function isKRTicker(ticker: string): boolean {
  return /^\d{6}$/.test(ticker);
}

function sourceClass(source: string | undefined): number {
  if (!source) return 9;
  return SOURCE_CLASS_PRIORITY[source] ?? 9;
}

function compareRelations(a: Relation, b: Relation, selfIsKR: boolean | null): number {
  const pa = TYPE_PRIORITY[a.relation_type] ?? 9;
  const pb = TYPE_PRIORITY[b.relation_type] ?? 9;
  if (pa !== pb) return pa - pb;
  const sca = sourceClass(a.source);
  const scb = sourceClass(b.source);
  if (sca !== scb) return sca - scb;
  if (selfIsKR !== null) {
    const aCross = isKRTicker(a.target_ticker) !== selfIsKR;
    const bCross = isKRTicker(b.target_ticker) !== selfIsKR;
    if (aCross !== bCross) return aCross ? -1 : 1;
  }
  const sa = (a.confidence ?? 0.5) * a.strength;
  const sb = (b.confidence ?? 0.5) * b.strength;
  return sb - sa;
}

// ─────────────────────────────────────────────────────────────
// Tier blocks (Core / Business)
// ─────────────────────────────────────────────────────────────

function TierBlock({
  tier,
  title,
  subtitle,
  rels,
}: {
  tier: "core" | "business";
  title: string;
  subtitle: string;
  rels: Relation[];
}) {
  // Cap per tier — core 는 8 (강조), business 는 8 (보통). 추가는 그래프.
  const CAP = 8;
  const isCore = tier === "core";
  const block =
    isCore
      ? "rounded-md border border-amber-500/40 dark:border-amber-500/30 bg-amber-500/5 px-3 py-2.5"
      : "rounded-md border border-[var(--surface-border)] bg-[var(--surface-card)] px-3 py-2.5";
  return (
    <div className={block}>
      <div className="mb-2">
        <h4
          className={
            isCore
              ? "text-sm font-semibold text-amber-700 dark:text-amber-300"
              : "text-sm font-semibold text-[var(--surface-text)]"
          }
        >
          {title}
        </h4>
        <p className="text-[11px] text-[var(--surface-text-subtle)] leading-snug">
          {subtitle}
        </p>
      </div>
      <ul className={isCore ? "space-y-2" : "space-y-1.5"}>
        {rels.slice(0, CAP).map((r, i) => (
          <TierRow
            key={`${r.target_ticker}-${r.relation_type}-${r.source ?? i}`}
            rel={r}
            isCore={isCore}
          />
        ))}
      </ul>
      {rels.length > CAP ? (
        <p className="mt-1.5 text-[11px] text-[var(--surface-text-subtle)]">
          + {rels.length - CAP}개 더 — 그래프에서 전체 보기
        </p>
      ) : null}
    </div>
  );
}

function TierRow({ rel, isCore }: { rel: Relation; isCore: boolean }) {
  const confidence = rel.confidence ?? 0.5;
  const conf = Math.round(confidence * 100);
  const strength = Math.round(rel.strength * 100);
  const sourceLabel = rel.source ? SOURCE_LABEL[rel.source] ?? rel.source : null;
  const change = rel.today_change_pct;
  const changeColor =
    change == null
      ? "text-[var(--surface-text-muted)]"
      : change > 0
        ? "text-red-600 dark:text-red-400"
        : change < 0
          ? "text-blue-600 dark:text-blue-400"
          : "text-[var(--surface-text-muted)]";

  const targetWeight = isCore ? "font-semibold" : "font-medium";
  const rowText = isCore ? "text-sm" : "text-xs";
  const rationale = rel.rationale?.trim() || null;

  const cc = rel.customer_concentration_pct;
  return (
    <li className={rowText}>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className={targetWeight}>{rel.target_name}</span>
        {rel.target_ticker && rel.target_ticker !== rel.target_name ? (
          <span className="text-[11px] text-[var(--surface-text-muted)]">
            ({rel.target_ticker})
          </span>
        ) : null}
        <span className="text-[11px] text-[var(--surface-text-muted)]">
          · {RELATION_LABEL[rel.relation_type] ?? rel.relation_type}
        </span>
        <SignalBadge direction={rel.signal_direction} />
        {change != null ? (
          <span className={`text-[11px] tabular-nums ${changeColor}`}>
            {change > 0 ? "+" : ""}
            {change.toFixed(1)}%
          </span>
        ) : null}
        {/* Codex I — 매출 의존 30%+ 면 lock-in risk 강조 badge. */}
        {cc != null && cc >= 30 ? (
          <span
            className="inline-flex items-center gap-0.5 rounded bg-red-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-red-700 dark:text-red-300 border border-red-500/30"
            title="매출 의존도 높음 — 이 고객의 발주가 끊기면 매출 직격"
          >
            🚨 매출 {cc.toFixed(0)}%
          </span>
        ) : cc != null && cc > 0 ? (
          <span
            className="text-[10px] text-[var(--surface-text-subtle)]"
            title="매출 의존도 정량 명시"
          >
            매출 {cc.toFixed(0)}%
          </span>
        ) : null}
      </div>
      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px] text-[var(--surface-text-subtle)]">
        <ConfidenceBar pct={conf} highlight={isCore} />
        <span className="tabular-nums">신뢰 {conf}%</span>
        <span className="tabular-nums">· 강도 {strength}%</span>
        {sourceLabel ? <span>· {sourceLabel}</span> : null}
        {rel.source_url ? (
          <a
            href={rel.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 dark:text-blue-400 hover:underline"
          >
            원문 ↗
          </a>
        ) : null}
      </div>
      {rationale ? (
        <p
          className={`mt-0.5 italic leading-snug ${
            isCore
              ? "text-xs text-[var(--surface-text-muted)]"
              : "text-[11px] text-[var(--surface-text-subtle)]"
          }`}
        >
          “{rationale}”
        </p>
      ) : null}
    </li>
  );
}

function ConfidenceBar({ pct, highlight }: { pct: number; highlight: boolean }) {
  const color = highlight
    ? "bg-amber-500/70 dark:bg-amber-400/70"
    : "bg-[var(--surface-text-muted)]";
  return (
    <span
      className="inline-block h-1 w-12 rounded bg-[var(--surface-border)] overflow-hidden align-middle"
      aria-hidden
    >
      <span
        className={`block h-full ${color}`}
        style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
      />
    </span>
  );
}

// ─────────────────────────────────────────────────────────────
// Context tier — 한 줄 chip pill 압축
// ─────────────────────────────────────────────────────────────

function ContextChips({ rels }: { rels: Relation[] }) {
  // Cap 20 정도 — 더 많으면 그래프로 안내. 가로 wrap.
  const CAP = 20;
  const shown = rels.slice(0, CAP);
  return (
    <div className="rounded-md border border-[var(--surface-border)]/70 px-3 py-2 bg-transparent">
      <div className="mb-1">
        <h4 className="text-xs font-medium text-[var(--surface-text-muted)]">
          🔗 컨텍스트 — 동종업계 · 그룹 · 테마
        </h4>
        <p className="text-[11px] text-[var(--surface-text-subtle)] leading-snug">
          같은 섹터·테마 lookup. 매매 baseline 아님, 분위기 파악용.
        </p>
      </div>
      <ul className="flex flex-wrap gap-1.5">
        {shown.map((r, i) => (
          <li key={`${r.target_ticker}-${r.relation_type}-${i}`}>
            <a
              href={`/stock/${r.target_ticker}`}
              className="inline-flex items-center gap-1 rounded-full border border-[var(--surface-border)] bg-[var(--surface-section-hover)] px-2 py-0.5 text-[11px] text-[var(--surface-text-muted)] hover:text-[var(--surface-text)] hover:border-[var(--surface-text-muted)]"
              title={`${RELATION_LABEL[r.relation_type] ?? r.relation_type} · 신뢰 ${Math.round((r.confidence ?? 0.5) * 100)}%`}
            >
              <span>{r.target_name}</span>
              {r.target_ticker && r.target_ticker !== r.target_name ? (
                <span className="text-[10px] text-[var(--surface-text-subtle)]">
                  {r.target_ticker}
                </span>
              ) : null}
            </a>
          </li>
        ))}
      </ul>
      {rels.length > CAP ? (
        <p className="mt-1.5 text-[11px] text-[var(--surface-text-subtle)]">
          + {rels.length - CAP}개 더 — 그래프에서 전체 보기
        </p>
      ) : null}
    </div>
  );
}

function SignalBadge({ direction }: { direction?: SignalDirection }) {
  if (direction === "inverse") {
    return (
      <span className="text-blue-600 dark:text-blue-400" title="역(zero-sum) 신호">
        ⇄
      </span>
    );
  }
  if (direction === "negative") {
    return (
      <span className="text-amber-600 dark:text-amber-400" title="부정 신호">
        ↓
      </span>
    );
  }
  return (
    <span className="text-red-600 dark:text-red-400" title="긍정 신호">
      ↑
    </span>
  );
}

// ─────────────────────────────────────────────────────────────
// Zero-sum (inverse competitor) dedicated callout (Codex D)
// ─────────────────────────────────────────────────────────────

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
                  {sourceLabel ? ` · ${sourceLabel}` : ""}
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
