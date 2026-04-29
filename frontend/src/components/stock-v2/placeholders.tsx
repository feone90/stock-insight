"use client";

/**
 * Placeholder components for sub-phase B–F.
 *
 * Each export is a stub with the correct prop type so `card-shell.tsx`
 * compiles today. Sub-phase B fills CardHeader / HeroChart / AtAGlancePanel /
 * CardFooter; sub-phase C+D fill the 7 sections; sub-phase E adds states.
 *
 * One file rather than 11 placeholder files — they get split out as each
 * sub-phase makes one of them real.
 */

import { SectionShell } from "./section-shell";

// Sub-phase B introduces the StockCard prop type; placeholders are zero-arg today.

export function CardHeader() {
  return (
    <header className="border-b border-[var(--surface-border)] p-4">
      <div className="text-2xl md:text-3xl font-bold">[CardHeader]</div>
      <div className="text-sm text-[var(--surface-text-muted)]">
        sub-phase B — ticker · name · market · stance · price · asof
      </div>
    </header>
  );
}

export function HeroChart() {
  return (
    <div className="h-60 md:h-80 border-b border-[var(--surface-border)] flex items-center justify-center text-[var(--surface-text-muted)]">
      [HeroChart] — sub-phase B (lightweight-charts v5 reuse)
    </div>
  );
}

export function AtAGlancePanel() {
  return (
    <div className="border-b border-[var(--surface-border)] bg-[var(--surface-glance)] p-4">
      <div className="text-base font-medium">[At-a-glance]</div>
      <div className="text-sm text-[var(--surface-text-muted)]">
        sub-phase B — Final Grade · Stance · Entry Stage 3-tile + one_line
      </div>
    </div>
  );
}

export function ThesisSection() {
  return (
    <SectionShell
      emoji="▣"
      title="종합 의견"
      defaultOpen
      highlight="glance"
      compact={<span className="text-sm">sub-phase C — supports/opposes/scenarios 1-line</span>}
      expanded={<div className="text-sm">sub-phase D — depth memo</div>}
    />
  );
}

export function TechMomentumSection() {
  return (
    <SectionShell
      emoji="📊"
      title="모멘텀 / 기술"
      compact={<span className="text-sm">sub-phase C — RSI / MA / RVOL 3-tile</span>}
      expanded={<div className="text-sm">sub-phase D — full indicators</div>}
    />
  );
}

export function RelationsSection() {
  return (
    <SectionShell
      emoji="🔗"
      title="관계"
      compact={<span className="text-sm">sub-phase C — peer / supply / theme 1-line</span>}
      expanded={
        <div className="text-sm">
          sub-phase D — relations table + [그래프로 보기 →] (P3 placeholder)
        </div>
      }
    />
  );
}

export function NewsSection() {
  return (
    <SectionShell
      emoji="📰"
      title="뉴스 / 이슈"
      compact={<span className="text-sm">sub-phase C — topic + impact emoji</span>}
      expanded={<div className="text-sm">sub-phase D — news list with summary</div>}
    />
  );
}

export function MacroSection() {
  return (
    <SectionShell
      emoji="🌐"
      title="매크로 / 사회 이슈"
      compact={<span className="text-sm">sub-phase C — VIX / FX / 미 10Y</span>}
      expanded={<div className="text-sm">sub-phase D — factor β + upcoming events</div>}
    />
  );
}

export function FundamentalsSection() {
  return (
    <SectionShell
      emoji="📐"
      title="펀더멘털"
      compact={<span className="text-sm">sub-phase C — PER / PBR / 시총 3-tile</span>}
      expanded={<div className="text-sm">sub-phase D — 5y z-score + dividend</div>}
    />
  );
}

export function DecisionSection() {
  return (
    <SectionShell
      emoji="✅"
      title="의사결정"
      defaultOpen
      highlight="decision"
      compact={
        <span className="text-sm">sub-phase C — stance + 기준 지지선 + 시나리오 한 줄</span>
      }
      expanded={
        <div className="text-sm">
          sub-phase D — scenarios + risk_threshold + &quot;참고용&quot; 면책
        </div>
      }
    />
  );
}

export function CardFooter() {
  return (
    <footer className="border-t border-[var(--surface-border)] p-4 flex items-center justify-between text-sm text-[var(--surface-text-muted)]">
      <span>[CardFooter] — sub-phase F (refresh state · 출처 N · 강제 갱신 · 분석에 질문)</span>
    </footer>
  );
}
