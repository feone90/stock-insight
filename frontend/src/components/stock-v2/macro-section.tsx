"use client";

import { Globe2 } from "lucide-react";
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
      icon={<Globe2 size={17} />}
      title="매크로"
      compact={
        <span>
          {parts.length > 0
            ? parts.join(" · ")
            : macro.one_line || "매크로 데이터 부족"}
        </span>
      }
      expanded={<MacroExpanded macro={macro} />}
      helpText={
        <div className="space-y-1.5">
          <p>
            <strong>지금 시장 전체 분위기</strong>를 보여주는 거시 지표들. 개별
            종목과 무관해 보여도 환율·금리가 흔들리면 한국/미국 주식 전체가
            같이 움직임.
          </p>
          <ul className="ml-3 space-y-0.5 list-disc">
            <li><strong>VIX (공포 지수)</strong> — 20 이상이면 시장 불안, 30+ 면 공포. 평소엔 12~18</li>
            <li><strong>USD/KRW (환율)</strong> — 원화 약세 = 한국 수출주 유리, 강세 = 내수주 유리</li>
            <li><strong>미 10년 국채 금리</strong> — 높을수록 성장주 부담. 4%+ 면 IT/AI 같은 고PER 종목 압박</li>
            <li><strong>연준 기준금리</strong> — 인하 사이클 = 위험자산 유리, 인상 = 안전자산 유리</li>
          </ul>
        </div>
      }
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
