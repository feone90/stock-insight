"use client";

import { Brain, LineChart, Moon, Newspaper, RefreshCw, RotateCw, Star, Sun } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { addFavorite, getStock, removeFavorite } from "@/services/api";
import { onUserChanged } from "@/services/user";
import { useStockCard } from "@/lib/use-stock-card";
import { useTheme } from "@/lib/use-theme";
import { AtAGlancePanel } from "./at-a-glance-panel";
import { CardHeader } from "./card-header";
import { DecisionSection } from "./decision-section";
import { EarningsAnalystSection } from "./earnings-analyst-section";
import { FlowSection } from "./flow-section";
import { FundamentalsSection } from "./fundamentals-section";
import { HeroChart } from "./hero-chart";
import { InsiderSection } from "./insider-section";
import { MacroSection } from "./macro-section";
import { NewsSection } from "./news-section";
import { CardFooter } from "./placeholders";
import { RelationsSection } from "./relations-section";
import { TechMomentumSection } from "./tech-momentum-section";
import { ThesisSection } from "./thesis-section";

// backend `ANALYSIS_COOLDOWN_SECONDS` 와 동기. 분석 1건 ~$0.25 라 무지성
// 클릭을 막아야 비용 안전. 백엔드가 429로도 막지만 frontend 단에서 disable
// 시키면 사용자가 클릭 자체를 안 함.
const REFRESH_COOLDOWN_MS = 5 * 60 * 1000;

function formatKoRelative(d: Date | null, now: number): string {
  if (!d) return "";
  const sec = Math.floor((now - d.getTime()) / 1000);
  if (sec < 60) return "방금 전";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}분 전`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}시간 전`;
  const day = Math.floor(hr / 24);
  return `${day}일 전`;
}

/**
 * StockCardPage — v2 stock card.
 *
 * Layout:
 *   <1024px → 1-column stack
 *   ≥1024px → 2-column. Left = chart + secondary sections;
 *             right = at-a-glance + decision + thesis ("what should I do?").
 *
 * Plan §4 + §17 (responsive). Sub-phases D adds citation drilldown,
 * E the full state matrix, F the footer + canonical-route flip.
 */
export function StockCardPage({ ticker }: { ticker: string }) {
  const { mode, toggle } = useTheme();
  const { card, state, refresh, refreshAll, refreshPrice, refreshNews, triggerAnalyze } =
    useStockCard(ticker);
  const refreshing = state === "analyzing";
  const [priceRefreshing, setPriceRefreshing] = useState(false);
  const [newsRefreshing, setNewsRefreshing] = useState(false);

  const handlePriceRefresh = async () => {
    if (priceRefreshing) return;
    setPriceRefreshing(true);
    try {
      await refreshPrice();
    } finally {
      setPriceRefreshing(false);
    }
  };

  const handleNewsRefresh = async () => {
    if (newsRefreshing) return;
    setNewsRefreshing(true);
    try {
      await refreshNews();
    } finally {
      setNewsRefreshing(false);
    }
  };

  // 즐겨찾기 — user picker 변경 시 reload (사용자별 분리)
  const [isFav, setIsFav] = useState(false);
  const [favBusy, setFavBusy] = useState(false);

  // cooldown 텍스트가 시간 흐르면서 갱신되도록 30s 주기 tick.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  const generatedAt = card?.generated_at ? new Date(card.generated_at) : null;
  const priceAsof = card?.price_asof ? new Date(card.price_asof) : null;
  const newsLatestAt = card?.news_latest_at ? new Date(card.news_latest_at) : null;
  const sinceMs = generatedAt ? now - generatedAt.getTime() : Infinity;
  const cooldownActive = sinceMs < REFRESH_COOLDOWN_MS;
  const cooldownLeftMin = cooldownActive
    ? Math.max(1, Math.ceil((REFRESH_COOLDOWN_MS - sinceMs) / 60000))
    : 0;

  useEffect(() => {
    const load = () => {
      getStock(ticker)
        .then((s) => setIsFav(s.is_favorite ?? false))
        .catch(() => setIsFav(false));
    };
    load();
    return onUserChanged(load);
  }, [ticker]);

  const toggleFav = async () => {
    if (favBusy) return;
    setFavBusy(true);
    try {
      if (isFav) await removeFavorite(ticker);
      else await addFavorite(ticker);
      setIsFav(!isFav);
    } finally {
      setFavBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--surface-bg)] text-[var(--surface-text)]">
      <div className="mx-auto max-w-[1200px] px-4 py-6 md:py-8">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-xs text-[var(--surface-text-subtle)]">
            {card ? card.ticker : ticker}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={toggleFav}
              disabled={favBusy}
              aria-label={isFav ? "즐겨찾기 해제" : "즐겨찾기 추가"}
              title={isFav ? "즐겨찾기 해제" : "즐겨찾기 추가"}
              className="inline-flex items-center justify-center rounded-md border border-[var(--surface-border)] bg-[var(--surface-card)] hover:bg-[var(--surface-section-hover)] transition-colors min-w-11 min-h-11 disabled:opacity-50"
            >
              <Star
                size={18}
                className={isFav ? "fill-yellow-400 text-yellow-400" : ""}
              />
            </button>
            <button
              type="button"
              onClick={toggle}
              aria-label={mode === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환"}
              className="inline-flex items-center justify-center rounded-md border border-[var(--surface-border)] bg-[var(--surface-card)] hover:bg-[var(--surface-section-hover)] transition-colors min-w-11 min-h-11"
            >
              {mode === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
          </div>
        </div>

        {card ? (
          <>
            <div className="mb-3">
              <button
                type="button"
                onClick={refreshAll}
                disabled={refreshing || cooldownActive}
                aria-label="전체 새로고침"
                title={
                  refreshing
                    ? "분석 중..."
                    : cooldownActive
                    ? `최근 분석됨 — ${cooldownLeftMin}분 뒤 다시 가능 ($0.25 비용 보호)`
                    : "가격·뉴스·공시 다 받고 AI 의견까지 새로 만들기 — LLM ~$0.25, 약 1분 소요. 5분 cooldown."
                }
                className="inline-flex items-center justify-center gap-1.5 rounded-md border border-blue-500/50 bg-blue-500/10 hover:bg-blue-500/20 text-blue-700 dark:text-blue-300 transition-colors px-4 min-h-11 text-sm font-medium w-full sm:w-auto disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <RotateCw size={16} className={refreshing ? "animate-spin" : ""} />
                <span>{refreshing ? "전체 새로고침 중..." : "전체 새로고침 (가격·뉴스·AI 의견)"}</span>
              </button>
              <p className="mt-1 text-[11px] text-[var(--surface-text-subtle)]">
                급할 땐 이 버튼 하나로 끝 — 약 1분, $0.25. 부분만 받고 싶으면 아래 3개.
              </p>
            </div>
            <div className="mb-4 grid grid-cols-1 sm:grid-cols-3 gap-2">
            <RefreshAction
              icon={<LineChart size={16} />}
              label="가격 새로고침"
              busyLabel="받는 중..."
              busy={priceRefreshing}
              onClick={handlePriceRefresh}
              timestamp={priceAsof}
              timestampPrefix="가격"
              now={now}
              tone="neutral"
              title="현재가·차트만 즉시 갱신 — 외부 API 1콜, ~2초. 30초 cooldown."
            />
            <RefreshAction
              icon={<Newspaper size={16} />}
              label="뉴스·공시 새로고침"
              busyLabel="받는 중..."
              busy={newsRefreshing}
              onClick={handleNewsRefresh}
              timestamp={newsLatestAt}
              timestampPrefix="최신 뉴스"
              now={now}
              tone="info"
              title="새 뉴스/공시 수집 — 새 뉴스 2건+이면 AI 의견도 자동 재생성. 2분 cooldown."
            />
            <RefreshAction
              icon={<Brain size={16} />}
              label={refreshing ? "분석 중..." : "AI 의견 다시"}
              busyLabel="분석 중..."
              busy={refreshing}
              disabled={cooldownActive}
              onClick={refresh}
              timestamp={generatedAt}
              timestampPrefix="AI 의견"
              cooldownLabel={cooldownActive ? `${cooldownLeftMin}분 뒤 가능` : null}
              now={now}
              tone="warning"
              title={
                refreshing
                  ? "AI 분석 중..."
                  : cooldownActive
                  ? `최근 분석됨 — ${cooldownLeftMin}분 뒤 다시 가능 ($0.25 비용 보호)`
                  : "전체 의견 재생성 — LLM 2-stage (~$0.25, 30~60초). 5분 cooldown."
              }
            />
            </div>
          </>
        ) : null}

        {state === "loading" && !card ? (
          <SkeletonCard />
        ) : state === "analyzing" && !card ? (
          <AnalyzingCard ticker={ticker} />
        ) : state === "error" && !card ? (
          <ErrorCard ticker={ticker} onAnalyze={triggerAnalyze} />
        ) : card ? (
          <article
            className="rounded-2xl border border-[var(--surface-border)] bg-[var(--surface-card)] overflow-hidden"
            style={{ boxShadow: "var(--surface-shadow)" }}
          >
            <CardHeader card={card} />

            <div className="grid gap-4 p-4 md:p-5 lg:grid-cols-[7fr_5fr] lg:gap-5">
              {/* Left — chart + secondary */}
              <div className="space-y-3 min-w-0">
                <HeroChart ticker={card.ticker} />
                <RelationsSection relations={card.relations} ticker={card.ticker} />
                <NewsSection news={card.news} political={card.political_signals} />
                <MacroSection macro={card.macro} />
                <FundamentalsSection fundamentals={card.fundamentals} />
                {card.flow ? <FlowSection flow={card.flow} /> : null}
                {card.insider ? <InsiderSection insider={card.insider} /> : null}
                {(card.earnings || card.analyst_rating || card.price_target) ? (
                  <EarningsAnalystSection
                    earnings={card.earnings}
                    rating={card.analyst_rating}
                    priceTarget={card.price_target}
                    currentPrice={card.price}
                  />
                ) : null}
                <TechMomentumSection technical={card.technical} />
              </div>

              {/* Right — what-do-I-do pane */}
              <aside className="space-y-3 min-w-0">
                <AtAGlancePanel card={card} />
                <DecisionSection decision={card.decision} citations={card.citations} />
                <ThesisSection
                  thesis={card.thesis}
                  stance={card.glance.stance}
                  citations={card.citations}
                />
              </aside>
            </div>

            <CardFooter citations={card.citations} />
          </article>
        ) : null}
      </div>
    </div>
  );
}

interface RefreshActionProps {
  icon: ReactNode;
  label: string;
  busyLabel: string;
  busy: boolean;
  disabled?: boolean;
  onClick: () => void | Promise<void>;
  timestamp: Date | null;
  timestampPrefix: string;
  cooldownLabel?: string | null;
  now: number;
  tone: "neutral" | "info" | "warning";
  title: string;
}

const TONE_CLASSES: Record<RefreshActionProps["tone"], string> = {
  neutral:
    "border border-[var(--surface-border)] bg-[var(--surface-card)] hover:bg-[var(--surface-section-hover)] text-[var(--surface-text)]",
  info: "border border-sky-500/40 bg-sky-500/10 hover:bg-sky-500/20 text-sky-700 dark:text-sky-300",
  warning:
    "border border-amber-500/40 bg-amber-500/10 hover:bg-amber-500/20 text-amber-700 dark:text-amber-300",
};

function RefreshAction({
  icon,
  label,
  busyLabel,
  busy,
  disabled,
  onClick,
  timestamp,
  timestampPrefix,
  cooldownLabel,
  now,
  tone,
  title,
}: RefreshActionProps) {
  const relative = formatKoRelative(timestamp, now);
  // cooldown 메시지가 있으면 그쪽이 더 actionable — "N분 뒤 가능" 가 사용자
  // 입장에선 "마지막 갱신" 보다 즉시 의미 있는 정보. 없으면 timestamp 표시.
  const subtext = cooldownLabel
    ? cooldownLabel
    : timestamp
    ? `${timestampPrefix}: ${relative}`
    : `${timestampPrefix} 데이터 없음`;
  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={onClick}
        disabled={busy || disabled}
        aria-label={label}
        title={title}
        className={`inline-flex items-center justify-center gap-1.5 rounded-md transition-colors px-2.5 sm:px-3 min-h-11 text-sm disabled:opacity-50 disabled:cursor-not-allowed ${TONE_CLASSES[tone]}`}
      >
        {busy ? <RefreshCw size={16} className="animate-spin" /> : icon}
        <span>{busy ? busyLabel : label}</span>
      </button>
      <span
        className="text-[11px] text-center text-[var(--surface-text-subtle)]"
        title={timestamp ? timestamp.toLocaleString("ko-KR") : undefined}
      >
        {subtext}
      </span>
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

function ErrorCard({
  ticker,
  onAnalyze,
}: {
  ticker: string;
  onAnalyze: () => Promise<void>;
}) {
  return (
    <div
      className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-6"
      style={{ boxShadow: "var(--surface-shadow)" }}
    >
      <p className="font-medium text-amber-700 dark:text-amber-300">
        {ticker.toUpperCase()} 카드가 아직 분석되지 않았어요.
      </p>
      <p className="mt-1 text-sm text-[var(--surface-text-muted)]">
        분석에 30초~1분 정도 걸려요. LLM 비용이 약간 발생합니다 (~$0.25).
      </p>
      <button
        type="button"
        onClick={onAnalyze}
        className="mt-3 inline-flex items-center rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
      >
        분석 시작
      </button>
    </div>
  );
}

function AnalyzingCard({ ticker }: { ticker: string }) {
  return (
    <div
      className="rounded-2xl border border-[var(--surface-border)] bg-[var(--surface-card)] p-12 text-center"
      style={{ boxShadow: "var(--surface-shadow)" }}
    >
      <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
      <p className="text-sm font-medium">{ticker.toUpperCase()} 분석 중...</p>
      <p className="mt-1 text-xs text-[var(--surface-text-muted)]">
        2-stage 파이프라인 (research → synthesize) — 30초~1분.
      </p>
    </div>
  );
}
