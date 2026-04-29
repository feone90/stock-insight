"use client";

/**
 * Only `CardFooter` stays a placeholder until sub-phase F.
 *
 * All other section components have graduated to their own files
 * (sub-phases B + C):
 *   card-header.tsx, hero-chart.tsx, at-a-glance-panel.tsx,
 *   thesis-section.tsx, tech-momentum-section.tsx, relations-section.tsx,
 *   news-section.tsx, macro-section.tsx, fundamentals-section.tsx,
 *   decision-section.tsx
 */

export function CardFooter() {
  return (
    <footer className="border-t border-[var(--surface-border)] px-5 py-4 flex items-center justify-between text-sm text-[var(--surface-text-muted)]">
      <span>분석 갱신 · 출처 N건 (sub-phase F 예정)</span>
      <span className="text-xs text-[var(--surface-text-subtle)]">
        강제 갱신 / 분석에 질문 — sub-phase F
      </span>
    </footer>
  );
}
