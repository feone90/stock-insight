"use client";

import type { Fundamentals } from "@/types/card";
import { SectionShell } from "./section-shell";

export function FundamentalsSection({
  fundamentals,
}: {
  fundamentals: Fundamentals;
}) {
  const parts: string[] = [];
  if (fundamentals.per != null) parts.push(`PER ${fundamentals.per.toFixed(1)}`);
  if (fundamentals.pbr != null) parts.push(`PBR ${fundamentals.pbr.toFixed(1)}`);
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

function FundamentalsExpanded({
  fundamentals,
}: {
  fundamentals: Fundamentals;
}) {
  const items: { label: string; value: string }[] = [];
  if (fundamentals.per != null)
    items.push({ label: "PER", value: fundamentals.per.toFixed(2) });
  if (fundamentals.pbr != null)
    items.push({ label: "PBR", value: fundamentals.pbr.toFixed(2) });
  if (fundamentals.market_cap_krw != null)
    items.push({
      label: "시가총액",
      value: formatCap(fundamentals.market_cap_krw),
    });
  if (fundamentals.dividend_yield != null)
    items.push({
      label: "배당수익률",
      value: `${fundamentals.dividend_yield.toFixed(2)}%`,
    });
  if (fundamentals.per_5y_z != null)
    items.push({
      label: "PER 5y z-score",
      value: fundamentals.per_5y_z.toFixed(2),
    });

  if (items.length === 0)
    return (
      <p className="text-sm text-[var(--surface-text-muted)]">재무 데이터 부족</p>
    );
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
      {items.map((i) => (
        <div key={i.label} className="flex justify-between">
          <dt className="text-[var(--surface-text-muted)]">{i.label}</dt>
          <dd className="tabular-nums">{i.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function formatCap(krw: number): string {
  if (krw >= 1e12) return `${(krw / 1e12).toFixed(1)}조`;
  if (krw >= 1e8) return `${(krw / 1e8).toFixed(0)}억`;
  return krw.toLocaleString();
}
