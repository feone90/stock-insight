"use client";

import type { MacroContext } from "@/types/card";
import { SectionShell } from "./section-shell";

export function MacroSection({ macro }: { macro: MacroContext }) {
  const parts: string[] = [];
  if (macro.vix != null) parts.push(`VIX ${macro.vix.toFixed(1)}`);
  const usdkrw = macro.fx_pairs?.["USD/KRW"];
  if (usdkrw != null) parts.push(`USD/KRW ${usdkrw.toFixed(0)}`);
  if (macro.us_10y != null) parts.push(`미 10Y ${macro.us_10y.toFixed(2)}%`);

  return (
    <SectionShell
      emoji="🌐"
      title="매크로"
      compact={
        <span>
          {parts.length > 0
            ? parts.join(" · ")
            : macro.one_line || "매크로 데이터 부족"}
        </span>
      }
      expanded={<MacroExpanded macro={macro} />}
    />
  );
}

function MacroExpanded({ macro }: { macro: MacroContext }) {
  const fxEntries = Object.entries(macro.fx_pairs ?? {});
  return (
    <div className="space-y-3 text-sm">
      {macro.one_line ? <p className="font-medium">{macro.one_line}</p> : null}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        {macro.vix != null ? (
          <div className="flex justify-between">
            <dt className="text-[var(--surface-text-muted)]">VIX</dt>
            <dd className="tabular-nums">{macro.vix.toFixed(2)}</dd>
          </div>
        ) : null}
        {macro.us_10y != null ? (
          <div className="flex justify-between">
            <dt className="text-[var(--surface-text-muted)]">미 10Y</dt>
            <dd className="tabular-nums">{macro.us_10y.toFixed(2)}%</dd>
          </div>
        ) : null}
        {fxEntries.map(([k, v]) => (
          <div key={k} className="flex justify-between">
            <dt className="text-[var(--surface-text-muted)]">{k}</dt>
            <dd className="tabular-nums">{v.toFixed(2)}</dd>
          </div>
        ))}
      </dl>

      {macro.upcoming_events?.length ? (
        <div>
          <div className="text-xs font-semibold mb-1">임박 매크로 일정</div>
          <ul className="text-xs text-[var(--surface-text-muted)] space-y-0.5">
            {macro.upcoming_events.map((e, i) => (
              <li key={i}>· {e}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
