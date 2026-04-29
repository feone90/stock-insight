"use client";

/**
 * Placeholder section components — sub-phase C/D fill content, sub-phase F
 * fills the footer.
 *
 * `CardHeader`, `HeroChart`, `AtAGlancePanel` graduated to their own files
 * during sub-phase B and are no longer placeholders.
 */

import { SectionShell } from "./section-shell";

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
