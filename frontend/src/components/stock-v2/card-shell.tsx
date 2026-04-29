"use client";

import { Moon, Sun } from "lucide-react";
import { useStockCard } from "@/lib/use-stock-card";
import { useTheme } from "@/lib/use-theme";
import { AtAGlancePanel } from "./at-a-glance-panel";
import { CardHeader } from "./card-header";
import { HeroChart } from "./hero-chart";
import {
  CardFooter,
  DecisionSection,
  FundamentalsSection,
  MacroSection,
  NewsSection,
  RelationsSection,
  TechMomentumSection,
  ThesisSection,
} from "./placeholders";

/**
 * StockCardPage — v2 stock card.
 *
 * Layout (plan §4 + post-A design pass):
 *   - <1024px (mobile/tablet): 1-column stack
 *   - ≥1024px (desktop): 2-column. Left = chart + secondary sections;
 *     right = at-a-glance + decision + thesis (the "what should I do?" pane).
 *   Header and footer stay full width.
 *
 * Sub-phases C/D fill section bodies; E adds the full state matrix; F
 * polishes footer + interactions and flips canonical /stock/[ticker].
 */
export function StockCardPage({ ticker }: { ticker: string }) {
  const { mode, toggle } = useTheme();
  const { card, state } = useStockCard(ticker);

  return (
    <div className="min-h-screen bg-[var(--surface-bg)] text-[var(--surface-text)]">
      <div className="mx-auto max-w-[1200px] px-4 py-6 md:py-8">
        {/* Top-nav row */}
        <div className="mb-4 flex items-center justify-between">
          <div className="text-xs text-[var(--surface-text-subtle)]">
            {card
              ? `v2 카드 · schema ${card.schema_version} · persona ${card.persona_version}`
              : `v2 카드 · ${ticker}`}
          </div>
          <button
            type="button"
            onClick={toggle}
            aria-label={mode === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환"}
            className="inline-flex items-center justify-center rounded-md border border-[var(--surface-border)] bg-[var(--surface-card)] hover:bg-[var(--surface-section-hover)] transition-colors min-w-11 min-h-11"
          >
            {mode === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>

        {state === "loading" && !card ? (
          <SkeletonCard />
        ) : state === "error" && !card ? (
          <ErrorCard />
        ) : card ? (
          <article
            className="rounded-2xl border border-[var(--surface-border)] bg-[var(--surface-card)] overflow-hidden"
            style={{ boxShadow: "var(--surface-shadow)" }}
          >
            <CardHeader card={card} />

            {/* Body — 2-column on desktop, stacked on mobile */}
            <div className="grid gap-4 p-4 md:p-5 lg:grid-cols-[7fr_5fr] lg:gap-5">
              {/* Left column — chart + secondary sections */}
              <div className="space-y-3 min-w-0">
                <HeroChart ticker={card.ticker} />
                <RelationsSection />
                <NewsSection />
                <MacroSection />
                <FundamentalsSection />
                <TechMomentumSection />
              </div>

              {/* Right column — what-do-I-do pane */}
              <aside className="space-y-3 min-w-0">
                <AtAGlancePanel card={card} />
                <DecisionSection />
                <ThesisSection />
              </aside>
            </div>

            <CardFooter />
          </article>
        ) : null}
      </div>
    </div>
  );
}

function SkeletonCard() {
  return (
    <div
      className="rounded-2xl border border-[var(--surface-border)] bg-[var(--surface-card)] p-12 text-center text-sm text-[var(--surface-text-muted)]"
      style={{ boxShadow: "var(--surface-shadow)" }}
    >
      분석 데이터 불러오는 중...
    </div>
  );
}

function ErrorCard() {
  return (
    <div
      className="rounded-2xl border border-red-500/30 bg-red-500/5 p-6"
      style={{ boxShadow: "var(--surface-shadow)" }}
    >
      <p className="font-medium text-red-700 dark:text-red-300">
        최근 분석 결과를 가져오지 못했어요.
      </p>
      <p className="mt-1 text-sm text-[var(--surface-text-muted)]">
        새로고침해주세요. (sub-phase E에서 재시도 버튼 추가 예정)
      </p>
    </div>
  );
}
