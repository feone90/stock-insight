"use client";

import type { TechMomentum } from "@/types/card";
import { SectionShell } from "./section-shell";

export function TechMomentumSection({ technical }: { technical: TechMomentum }) {
  const parts: string[] = [];
  if (technical.rsi_14 != null) parts.push(`RSI ${technical.rsi_14.toFixed(0)}`);
  if (technical.ma_stack) parts.push(technical.ma_stack);
  if (technical.rvol_20 != null) parts.push(`RVOL ${technical.rvol_20.toFixed(1)}x`);

  return (
    <SectionShell
      emoji="📊"
      title="모멘텀 / 기술"
      compact={
        <span>
          {parts.length > 0 ? parts.join(" · ") : technical.summary_line || "지표 데이터 부족"}
        </span>
      }
      expanded={<TechExpanded tech={technical} />}
    />
  );
}

function TechExpanded({ tech }: { tech: TechMomentum }) {
  const items: { label: string; value: string | null }[] = [
    { label: "RSI 14", value: tech.rsi_14?.toFixed(1) ?? null },
    { label: "MFI 14", value: tech.mfi_14?.toFixed(1) ?? null },
    { label: "ATR %", value: tech.atr_pct?.toFixed(2) ?? null },
    { label: "CMF 20", value: tech.cmf_20?.toFixed(2) ?? null },
    { label: "OBV ratio", value: tech.obv_ratio?.toFixed(2) ?? null },
    { label: "RVOL 20", value: tech.rvol_20 != null ? `${tech.rvol_20.toFixed(1)}x` : null },
    { label: "MA stack", value: tech.ma_stack },
    { label: "박스 위치", value: tech.box_position },
  ].filter((i) => i.value != null);

  return (
    <div className="space-y-2 text-sm">
      {tech.summary_line ? <p className="font-medium">{tech.summary_line}</p> : null}
      {items.length === 0 ? (
        <p className="text-[var(--surface-text-muted)]">지표 데이터 부족</p>
      ) : (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          {items.map((i) => (
            <div key={i.label} className="flex justify-between">
              <dt className="text-[var(--surface-text-muted)]">{i.label}</dt>
              <dd className="tabular-nums">{i.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
