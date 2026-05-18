"use client";

import type { PriceMoveCause, RecentPriceMove } from "@/types/card";

/**
 * 헤더 가격 아래 full-width band — "최근 N거래일 X% 왜?" 답.
 *
 * 사용자 피드백 (2026-05-19): "한미반도체가 며칠 떨어지는데 카드 봤을 때
 * 왜 떨어지는지 안 보임". 가격 본 직후 *원인* 답이 보여야 가족 사용자가
 * 매수/매도 판단 가능.
 */

const WINDOW_LABEL: Record<RecentPriceMove["primary_window"], string> = {
  "5d": "최근 5거래일",
  "14d": "최근 14거래일",
  "30d": "최근 30거래일",
};

const EVIDENCE_LABEL: Record<PriceMoveCause["evidence_kind"], string> = {
  news: "뉴스",
  disclosure: "공시",
  political: "정치 시그널",
  flow: "수급",
  valuation: "밸류에이션",
  peer_move: "동종업계",
  knowledge: "분석가 지식",
};

const CONFIDENCE_LABEL: Record<PriceMoveCause["confidence"], string> = {
  high: "확실",
  medium: "유력",
  low: "추정",
};

const CONFIDENCE_COLOR: Record<PriceMoveCause["confidence"], string> = {
  high: "text-emerald-700 dark:text-emerald-300 border-emerald-500/40 bg-emerald-500/10",
  medium: "text-sky-700 dark:text-sky-300 border-sky-500/40 bg-sky-500/10",
  low: "text-[var(--surface-text-muted)] border-[var(--surface-border)] bg-[var(--surface-section-hover)]",
};

export function RecentPriceMoveSection({ move }: { move: RecentPriceMove }) {
  const primaryPct =
    move.primary_window === "5d"
      ? move.return_5d_pct
      : move.primary_window === "14d"
      ? move.return_14d_pct
      : move.return_30d_pct;

  const isNeg = primaryPct != null && primaryPct < 0;
  // 한국 관습: 상승=빨강, 하락=파랑
  const accent =
    primaryPct == null
      ? "border-[var(--surface-border)] bg-[var(--surface-card)]"
      : isNeg
      ? "border-blue-500/30 bg-blue-500/5"
      : "border-red-500/30 bg-red-500/5";

  return (
    <section
      className={`mx-4 md:mx-5 my-3 rounded-lg border ${accent} px-4 py-3`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-[var(--surface-text)]">
          📉 최근 가격 움직임
        </h3>
        <ReturnsBar move={move} />
      </div>
      <p className="mt-1 text-sm leading-relaxed text-[var(--surface-text)]">
        {move.one_line}
      </p>
      {move.causes.length > 0 ? (
        <ul className="mt-2.5 space-y-1.5">
          {move.causes.map((c, i) => (
            <CauseRow key={i} cause={c} />
          ))}
        </ul>
      ) : null}
      {move.unknown_or_unconfirmed ? (
        <p className="mt-2 text-xs italic text-[var(--surface-text-muted)] leading-snug">
          ⚠️ {move.unknown_or_unconfirmed}
        </p>
      ) : null}
    </section>
  );
}

function ReturnsBar({ move }: { move: RecentPriceMove }) {
  const items: Array<{ label: string; pct: number | null | undefined }> = [
    { label: "5일", pct: move.return_5d_pct },
    { label: "14일", pct: move.return_14d_pct },
    { label: "30일", pct: move.return_30d_pct },
  ];
  return (
    <div className="flex items-baseline gap-3 text-[11px]">
      {items.map((it) => {
        const cls =
          it.pct == null
            ? "text-[var(--surface-text-muted)]"
            : it.pct < 0
            ? "text-blue-600 dark:text-blue-400"
            : it.pct > 0
            ? "text-red-600 dark:text-red-400"
            : "text-[var(--surface-text-muted)]";
        return (
          <span key={it.label} className="tabular-nums">
            <span className="text-[var(--surface-text-subtle)]">{it.label} </span>
            <span className={`font-semibold ${cls}`}>
              {it.pct == null
                ? "—"
                : `${it.pct > 0 ? "+" : ""}${it.pct.toFixed(1)}%`}
            </span>
          </span>
        );
      })}
    </div>
  );
}

function CauseRow({ cause }: { cause: PriceMoveCause }) {
  const isKnowledge = cause.evidence_kind === "knowledge";
  const cutoffHigh = cause.knowledge_cutoff_risk === "high";
  return (
    <li className="text-xs">
      <div className="flex flex-wrap items-baseline gap-1.5">
        <span
          className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium ${CONFIDENCE_COLOR[cause.confidence]}`}
        >
          {CONFIDENCE_LABEL[cause.confidence]}
        </span>
        <span className="text-[10px] text-[var(--surface-text-subtle)]">
          · {EVIDENCE_LABEL[cause.evidence_kind]}
          {cause.evidence_date ? ` · ${cause.evidence_date.slice(0, 10)}` : ""}
        </span>
        {isKnowledge && cutoffHigh ? (
          <span
            className="inline-flex items-center rounded bg-amber-500/15 border border-amber-500/30 px-1 py-0.5 text-[9px] text-amber-700 dark:text-amber-300"
            title="LLM 학습 시점 이후 변동 가능 — IR 또는 최신 자료 확인 권장"
          >
            최신성 ⚠️
          </span>
        ) : null}
        <span className="text-[var(--surface-text)]">{cause.text}</span>
      </div>
      {cause.evidence_quote ? (
        <p className="mt-0.5 italic text-[11px] text-[var(--surface-text-muted)] leading-snug">
          “{cause.evidence_quote}”
        </p>
      ) : null}
    </li>
  );
}
