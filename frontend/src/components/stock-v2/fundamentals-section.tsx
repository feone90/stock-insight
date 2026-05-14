"use client";

import type { Fundamentals } from "@/types/card";
import { SectionShell } from "./section-shell";

/**
 * 펀더멘털 섹션 — 카드 UI 카피 가이드(memory: feedback_card_user_facing_copy)
 * 적용. 약어(PER/PBR) 절대 노출 X, "주가가 이익의 N배" 식 비유로 변환.
 * 가족(40~60대 비전공자)이 한 번 읽고 행동 결정 가능하게.
 */
export function FundamentalsSection({
  fundamentals,
}: {
  fundamentals: Fundamentals;
}) {
  const parts: string[] = [];
  if (fundamentals.per != null)
    parts.push(`이익 대비 ${fundamentals.per.toFixed(1)}배`);
  if (fundamentals.pbr != null)
    parts.push(`자산 대비 ${fundamentals.pbr.toFixed(1)}배`);
  if (fundamentals.market_cap_krw != null)
    parts.push(`시총 ${formatCap(fundamentals.market_cap_krw)}`);

  return (
    <SectionShell
      emoji="📐"
      title="펀더멘털"
      compact={
        <span>{parts.length > 0 ? parts.join(" · ") : "재무 데이터 부족"}</span>
      }
      expanded={<FundamentalsExpanded fundamentals={fundamentals} />}
    />
  );
}

interface ExpandedItem {
  label: string;
  value: string;
  help?: string;
}

function FundamentalsExpanded({
  fundamentals,
}: {
  fundamentals: Fundamentals;
}) {
  const items: ExpandedItem[] = [];

  if (fundamentals.per != null) {
    items.push({
      label: "이익 대비 주가",
      value: `${fundamentals.per.toFixed(2)}배`,
      help: perHelp(fundamentals.per),
    });
  }
  if (fundamentals.pbr != null) {
    items.push({
      label: "순자산 대비 주가",
      value: `${fundamentals.pbr.toFixed(2)}배`,
      help: pbrHelp(fundamentals.pbr),
    });
  }
  if (fundamentals.market_cap_krw != null) {
    items.push({
      label: "기업 시가총액",
      value: formatCap(fundamentals.market_cap_krw),
    });
  }
  if (fundamentals.dividend_yield != null) {
    items.push({
      label: "연 배당수익률",
      value: `${fundamentals.dividend_yield.toFixed(2)}%`,
      help:
        fundamentals.dividend_yield >= 3
          ? "배당이 후한 편 (예금 금리 수준)"
          : fundamentals.dividend_yield > 0
          ? "배당 있음"
          : undefined,
    });
  }
  if (fundamentals.per_5y_z != null) {
    items.push({
      label: "이익배수 5년 추이",
      value: fundamentals.per_5y_z.toFixed(2),
      help:
        fundamentals.per_5y_z > 1
          ? "지난 5년 평균보다 높음 → 고평가 구간"
          : fundamentals.per_5y_z < -1
          ? "지난 5년 평균보다 낮음 → 저평가 구간"
          : "지난 5년 평균과 비슷",
    });
  }

  const source = fundamentals.source_label?.trim() || null;

  if (items.length === 0) {
    return (
      <div className="space-y-1">
        <p className="text-sm text-[var(--surface-text-muted)]">
          재무 데이터 부족
        </p>
        {source ? (
          <p className="text-[11px] italic text-[var(--surface-text-subtle)]">
            출처: {source}
          </p>
        ) : null}
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <dl className="space-y-1.5 text-xs">
        {items.map((i) => (
          <div key={i.label} className="grid grid-cols-[1fr_auto] gap-x-3">
            <dt className="text-[var(--surface-text-muted)]">{i.label}</dt>
            <dd className="tabular-nums font-medium">{i.value}</dd>
            {i.help ? (
              <dd className="col-span-2 text-[11px] text-[var(--surface-text-subtle)]">
                → {i.help}
              </dd>
            ) : null}
          </div>
        ))}
      </dl>
      {source ? (
        <p className="text-[11px] italic text-[var(--surface-text-subtle)]">
          출처: {source}
        </p>
      ) : null}
    </div>
  );
}

// "주가가 1년 이익의 N배" 비유. baseline 비교는 데이터가 와야 정확하므로
// 일반적 해석만 표시. 산업별 기준은 추후 백엔드에서 peer_avg_per 와 함께
// 카드 schema 에 들어오면 정밀화.
function perHelp(per: number): string {
  if (per <= 0) return "이익이 마이너스 (적자 상태)";
  if (per < 8) return "주가가 1년 이익의 8배 미만 — 저평가 신호 가능성";
  if (per < 15) return "1년 이익의 평균 범위 (전통주 기준)";
  if (per < 25) return "1년 이익의 다소 높은 배수 (성장 기대 반영)";
  return "1년 이익 대비 매우 높음 — 성장 프리미엄 또는 거품";
}

function pbrHelp(pbr: number): string {
  if (pbr <= 0) return "자산 산정 불가";
  if (pbr < 1) return "회사 순자산보다 주가가 낮음 (자산 가치 미반영)";
  if (pbr < 2) return "회사 자산의 1~2배 수준 — 평균 범위";
  if (pbr < 4) return "자산 대비 2~4배 — 다소 높은 평가";
  return "자산 대비 매우 높음 — 무형자산/성장성 프리미엄";
}

function formatCap(krw: number): string {
  if (krw >= 1e12) return `${(krw / 1e12).toFixed(1)}조`;
  if (krw >= 1e8) return `${(krw / 1e8).toFixed(0)}억`;
  return krw.toLocaleString();
}
