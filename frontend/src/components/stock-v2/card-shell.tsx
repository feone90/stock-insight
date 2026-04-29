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
 * StockCardPage shell — outer container, theme toggle, fetch hook, and the
 * 7-section accordion. Sub-phase C/D fill the section bodies; sub-phase E
 * adds the loading/empty/error/stale states; sub-phase F finishes the footer.
 *
 * Plan §4 (component tree), §5 (data flow).
 */
export function StockCardPage({ ticker }: { ticker: string }) {
  const { mode, toggle } = useTheme();
  const { card, state } = useStockCard(ticker);

  return (
    <div className="min-h-screen bg-[var(--surface-card)] text-[var(--surface-text)]">
      <div className="mx-auto max-w-[1024px] px-4 py-6">
        {/* Top-nav row — toggle + meta */}
        <div className="mb-4 flex items-center justify-between">
          <div className="text-xs text-[var(--surface-text-muted)]">
            {card
              ? `v2 카드 · schema ${card.schema_version} · persona ${card.persona_version}`
              : `v2 카드 · ${ticker}`}
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

        {/* States are sub-phase E's full responsibility; this is the minimum
            so the page doesn't render with `null` props before fetch resolves. */}
        {state === "loading" && !card ? (
          <div className="rounded-lg border border-[var(--surface-border)] bg-[var(--surface-card)] p-12 text-center text-sm text-[var(--surface-text-muted)]">
            분석 데이터 불러오는 중...
          </div>
        ) : state === "error" && !card ? (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-6 text-sm">
            <p className="font-medium text-red-700 dark:text-red-300">
              최근 분석 결과를 가져오지 못했어요.
            </p>
            <p className="mt-1 text-[var(--surface-text-muted)]">
              새로고침해주세요. (sub-phase E에서 재시도 버튼 추가 예정)
            </p>
          </div>
        ) : card ? (
          <article className="rounded-lg border border-[var(--surface-border)] bg-[var(--surface-card)] overflow-hidden">
            <CardHeader card={card} />
            <HeroChart ticker={card.ticker} />
            <AtAGlancePanel card={card} />
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
        ) : null}
      </div>
    </div>
  );
}
