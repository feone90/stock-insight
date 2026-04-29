"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/lib/use-theme";
import {
  AtAGlancePanel,
  CardFooter,
  CardHeader,
  DecisionSection,
  FundamentalsSection,
  HeroChart,
  MacroSection,
  NewsSection,
  RelationsSection,
  TechMomentumSection,
  ThesisSection,
} from "./placeholders";

/**
 * StockCardPage shell — card outer container, theme toggle, and 7-section
 * accordion. Concrete content is filled across sub-phase B–F.
 *
 * Plan §4 (component tree).
 */
export function StockCardPage({ ticker }: { ticker: string }) {
  const { mode, toggle } = useTheme();

  return (
    <div className="min-h-screen bg-[var(--surface-card)] text-[var(--surface-text)]">
      <div className="mx-auto max-w-[1024px] px-4 py-6">
        {/* Top-nav row — toggle is the only chrome in sub-phase A */}
        <div className="mb-4 flex items-center justify-between">
          <div className="text-xs text-[var(--surface-text-muted)]">
            ticker: {ticker} · v2 카드 (sub-phase A scaffold)
          </div>
          <button
            type="button"
            onClick={toggle}
            aria-label={mode === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환"}
            className="inline-flex items-center justify-center rounded-md border border-[var(--surface-border)] hover:bg-[var(--surface-section)] min-w-11 min-h-11"
          >
            {mode === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>

        <article className="rounded-lg border border-[var(--surface-border)] bg-[var(--surface-card)] overflow-hidden">
          {/* Server data not wired yet — pass null until sub-phase B */}
          <CardHeader />
          <HeroChart />
          <AtAGlancePanel />
          <div className="p-4 space-y-3">
            <ThesisSection />
            <TechMomentumSection />
            <RelationsSection />
            <NewsSection />
            <MacroSection />
            <FundamentalsSection />
            <DecisionSection />
          </div>
          <CardFooter />
        </article>
      </div>
    </div>
  );
}
