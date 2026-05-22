"use client";

import {
  ArrowLeft,
  ArrowRight,
  Brain,
  ChevronDown,
  Home,
  LineChart,
  List,
  Moon,
  Newspaper,
  RefreshCw,
  RotateCw,
  Sparkles,
  Star,
  Sun,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { addFavorite, getFavorites, getStock, removeFavorite } from "@/services/api";
import { getActiveUser, onUserChanged } from "@/services/user";
import { isMarketOpen } from "@/lib/markets";
import { useStockCard } from "@/lib/use-stock-card";
import { useTheme } from "@/lib/use-theme";
import type { Stock } from "@/types/stock";
import { AtAGlancePanel } from "./at-a-glance-panel";
import { AnalysisHistorySection } from "./analysis-history-section";
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
import { RecentPriceMoveSection } from "./recent-price-move-section";
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
  const router = useRouter();
  const { mode, toggle } = useTheme();
  const { card, state, refresh, refreshAll, refreshPrice, refreshNews, triggerAnalyze } =
    useStockCard(ticker);
  const refreshing = state === "analyzing";
  const [priceRefreshing, setPriceRefreshing] = useState(false);
  const [newsRefreshing, setNewsRefreshing] = useState(false);
  // refreshNews 후 backend hint 표시용 — "AI 의견도 갱신 중" / "그대로".
  // 7초 뒤 자동 사라짐 (timestamp 줄로 돌아감).
  const [newsHint, setNewsHint] = useState<string | null>(null);

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
    setNewsHint(null);
    try {
      const result = await refreshNews();
      if (result) {
        setNewsHint(
          result.aiRefreshLikely
            ? "AI 의견도 같이 갱신 중..."
            : "새 뉴스 없음 — AI 의견은 그대로",
        );
        setTimeout(() => setNewsHint(null), 7000);
      }
    } finally {
      setNewsRefreshing(false);
    }
  };

  // 즐겨찾기 — user picker 변경 시 reload (사용자별 분리)
  const [isFav, setIsFav] = useState(false);
  const [favBusy, setFavBusy] = useState(false);
  const [favorites, setFavorites] = useState<Stock[]>([]);
  const [favoritesOpen, setFavoritesOpen] = useState(false);
  const [activeUser, setActiveUserName] = useState<string | null>(null);

  // cooldown 텍스트가 시간 흐르면서 갱신되도록 30s 주기 tick.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  // 2026-05-18 — 자동 가격 polling. 30초마다 + tab visible + 장 개장 중일
  // 때만. backend price_refresh cooldown 이 30s — 자연스러운 하한선.
  // 장 외 시간엔 가격 자체 안 변하니 yfinance/pykrx 호출 절약.
  // KR: 평일 09:00-15:30 KST. US: 평일 22:30-05:00 KST.
  const cardMarket = card?.market;
  useEffect(() => {
    if (!cardMarket) return;
    const tick = () => {
      if (
        document.visibilityState === "visible" &&
        isMarketOpen(cardMarket)
      ) {
        refreshPrice().catch(() => {});
      }
    };
    const id = setInterval(tick, 30_000);
    document.addEventListener("visibilitychange", tick);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [refreshPrice, cardMarket]);

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
      setActiveUserName(getActiveUser());
      getStock(ticker)
        .then((s) => setIsFav(s.is_favorite ?? false))
        .catch(() => setIsFav(false));
      getFavorites()
        .then((items) => setFavorites(items))
        .catch(() => setFavorites([]));
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
      setFavorites((items) =>
        isFav ? items.filter((item) => item.ticker !== ticker) : items,
      );
      getFavorites()
        .then((items) => setFavorites(items))
        .catch(() => {});
    } finally {
      setFavBusy(false);
    }
  };

  const handleBack = () => {
    if (typeof window === "undefined") {
      router.push("/");
      return;
    }
    const sameOriginReferrer =
      document.referrer && new URL(document.referrer).origin === window.location.origin;
    if (sameOriginReferrer && window.history.length > 1) {
      router.back();
    } else {
      router.push("/");
    }
  };

  return (
    <div className="min-h-screen bg-[var(--surface-bg)] text-[var(--surface-text)]">
      <div className="mx-auto max-w-[1200px] px-4 py-6 md:py-8">
        <StockLocalNav
          ticker={ticker}
          stockName={card?.name_ko || card?.name_en}
          activeUser={activeUser}
          favorites={favorites}
          favoritesOpen={favoritesOpen}
          onToggleFavorites={() => setFavoritesOpen((v) => !v)}
          onBack={handleBack}
          isFav={isFav}
          favBusy={favBusy}
          onToggleFav={toggleFav}
          themeMode={mode}
          onToggleTheme={toggle}
        />

        {card ? (
          <>
            <RefreshCommandBar
              refreshing={refreshing}
              priceRefreshing={priceRefreshing}
              newsRefreshing={newsRefreshing}
              cooldownActive={cooldownActive}
              cooldownLeftMin={cooldownLeftMin}
              refreshAll={refreshAll}
              handlePriceRefresh={handlePriceRefresh}
              handleNewsRefresh={handleNewsRefresh}
              refresh={refresh}
              priceAsof={priceAsof}
              newsLatestAt={newsLatestAt}
              generatedAt={generatedAt}
              newsHint={newsHint}
              now={now}
            />
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

            {/* 2026-05-19 — 헤더 바로 아래 "왜 떨어졌나/올랐나" 답 layer. */}
            {card.recent_price_move ? (
              <RecentPriceMoveSection move={card.recent_price_move} />
            ) : null}

            <div className="grid gap-4 p-4 md:p-5 lg:grid-cols-[7fr_5fr] lg:gap-5">
              {/* Left — chart + secondary */}
              <div className="space-y-3 min-w-0">
                <HeroChart ticker={card.ticker} priceAsof={card.price_asof} />
                <AnalysisHistorySection ticker={card.ticker} />
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

function RefreshCommandBar({
  refreshing,
  priceRefreshing,
  newsRefreshing,
  cooldownActive,
  cooldownLeftMin,
  refreshAll,
  handlePriceRefresh,
  handleNewsRefresh,
  refresh,
  priceAsof,
  newsLatestAt,
  generatedAt,
  newsHint,
  now,
}: {
  refreshing: boolean;
  priceRefreshing: boolean;
  newsRefreshing: boolean;
  cooldownActive: boolean;
  cooldownLeftMin: number;
  refreshAll: () => Promise<void>;
  handlePriceRefresh: () => Promise<void>;
  handleNewsRefresh: () => Promise<void>;
  refresh: () => Promise<void>;
  priceAsof: Date | null;
  newsLatestAt: Date | null;
  generatedAt: Date | null;
  newsHint: string | null;
  now: number;
}) {
  const fullTitle = refreshing
    ? "분석 중..."
    : cooldownActive
      ? `최근 분석됨 — ${cooldownLeftMin}분 뒤 다시 가능 ($0.25 비용 보호)`
      : "가격·뉴스·공시를 먼저 받고, 마지막에 AI 의견까지 새로 만듭니다. LLM ~$0.25, 약 1분 소요.";

  return (
    <section className="mb-4 rounded-xl border border-blue-500/25 bg-blue-500/[0.04] p-2.5 sm:p-3">
      <div className="grid gap-2 lg:grid-cols-[minmax(260px,1.1fr)_minmax(420px,1.9fr)] lg:items-stretch">
        <div className="rounded-lg border border-blue-500/35 bg-blue-500/10 p-2">
          <button
            type="button"
            onClick={refreshAll}
            disabled={refreshing || cooldownActive}
            title={fullTitle}
            className="flex min-h-12 w-full items-center justify-center gap-2 rounded-md bg-blue-600 px-3 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {refreshing ? <RefreshCw size={17} className="animate-spin" /> : <RotateCw size={17} />}
            {refreshing ? "전체 분석 중..." : "전체 새로고침"}
          </button>
          <div className="mt-2 flex flex-wrap items-center justify-center gap-1.5 text-[11px] text-blue-700 dark:text-blue-300">
            <PipelineStep icon={<LineChart size={12} />} label="가격" />
            <ArrowRight size={12} />
            <PipelineStep icon={<Newspaper size={12} />} label="뉴스·공시" />
            <ArrowRight size={12} />
            <PipelineStep icon={<Brain size={12} />} label="AI 의견" />
          </div>
          <p className="mt-1.5 text-center text-[11px] text-[var(--surface-text-subtle)]">
            {cooldownActive ? `${cooldownLeftMin}분 뒤 다시 가능` : "세 작업을 순서대로 실행"}
          </p>
        </div>

        <div className="rounded-lg border border-[var(--surface-border)] bg-[var(--surface-card)]/80 p-2">
          <div className="mb-1.5 flex items-center gap-1.5 px-1 text-[11px] font-medium text-[var(--surface-text-muted)]">
            <Sparkles size={13} />
            세부 새로고침
          </div>
          <div className="grid grid-cols-3 gap-1.5 sm:gap-2">
            <RefreshAction
              icon={<LineChart size={16} />}
              label="가격"
              fullLabel="가격만"
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
              label="뉴스"
              fullLabel="뉴스·공시"
              busyLabel="받는 중..."
              busy={newsRefreshing}
              onClick={handleNewsRefresh}
              timestamp={newsLatestAt}
              timestampPrefix="뉴스"
              now={now}
              tone="info"
              title="새 뉴스/공시 수집 — 새 뉴스 1건+이면 AI 의견도 자동 재생성. 2분 cooldown."
              overrideSubtext={newsHint}
            />
            <RefreshAction
              icon={<Brain size={16} />}
              label={refreshing ? "분석" : "AI"}
              fullLabel="AI 의견"
              busyLabel="분석 중..."
              busy={refreshing}
              disabled={cooldownActive}
              onClick={refresh}
              timestamp={generatedAt}
              timestampPrefix="AI"
              cooldownLabel={cooldownActive ? `${cooldownLeftMin}분 뒤` : null}
              now={now}
              tone="warning"
              title={
                refreshing
                  ? "AI 분석 중..."
                  : cooldownActive
                    ? `최근 분석됨 — ${cooldownLeftMin}분 뒤 다시 가능 ($0.25 비용 보호)`
                    : "현재 데이터로 AI 의견만 다시 생성 — LLM 2-stage (~$0.25, 30~60초). 5분 cooldown."
              }
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function StockLocalNav({
  ticker,
  stockName,
  activeUser,
  favorites,
  favoritesOpen,
  onToggleFavorites,
  onBack,
  isFav,
  favBusy,
  onToggleFav,
  themeMode,
  onToggleTheme,
}: {
  ticker: string;
  stockName?: string;
  activeUser: string | null;
  favorites: Stock[];
  favoritesOpen: boolean;
  onToggleFavorites: () => void;
  onBack: () => void;
  isFav: boolean;
  favBusy: boolean;
  onToggleFav: () => Promise<void>;
  themeMode: "dark" | "light";
  onToggleTheme: () => void;
}) {
  const normalizedTicker = ticker.toUpperCase();
  const favoriteCount = favorites.length;

  return (
    <section className="mb-4 overflow-hidden rounded-xl border border-[var(--surface-border)] bg-[var(--surface-card)]/80">
      <div className="flex flex-col gap-2 p-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            onClick={onBack}
            aria-label="이전 화면으로 이동"
            title="이전 화면"
            className="inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded-md border border-[var(--surface-border)] bg-[var(--surface-section)] px-2.5 text-sm font-medium text-[var(--surface-text)] transition-colors hover:bg-[var(--surface-section-hover)]"
          >
            <ArrowLeft size={17} />
            <span className="hidden sm:inline">뒤로</span>
          </button>
          <Link
            href="/"
            title="홈의 즐겨찾기 목록으로 이동"
            className="inline-flex min-h-10 shrink-0 items-center justify-center rounded-md border border-[var(--surface-border)] bg-[var(--surface-section)] px-2.5 text-[var(--surface-text-muted)] transition-colors hover:bg-[var(--surface-section-hover)] hover:text-[var(--surface-text)]"
          >
            <Home size={17} />
          </Link>
          <div className="min-w-0 border-l border-[var(--surface-border)] pl-3">
            <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--surface-text-subtle)]">
              종목 상세
            </div>
            <div className="flex min-w-0 items-center gap-2">
              <span className="font-semibold text-[var(--surface-text)]">{normalizedTicker}</span>
              {stockName ? (
                <span className="truncate text-sm text-[var(--surface-text-muted)]">
                  {stockName}
                </span>
              ) : null}
            </div>
          </div>
        </div>

        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            onClick={onToggleFavorites}
            aria-expanded={favoritesOpen}
            className="inline-flex min-h-10 min-w-0 flex-1 items-center justify-center gap-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 text-sm font-medium text-amber-700 transition-colors hover:bg-amber-500/20 sm:flex-none dark:text-amber-300"
            title="현재 사용자의 즐겨찾기 종목 빠른 전환"
          >
            <List size={16} />
            <span className="truncate">
              {activeUser ? `${activeUser} 관심목록` : "내 즐겨찾기"}
            </span>
            <span className="rounded border border-amber-500/25 px-1.5 py-0.5 text-[11px] leading-none">
              {favoriteCount}
            </span>
            <ChevronDown
              size={15}
              className={`transition-transform ${favoritesOpen ? "rotate-180" : ""}`}
            />
          </button>
          <button
            type="button"
            onClick={onToggleFav}
            disabled={favBusy}
            aria-label={isFav ? "즐겨찾기 해제" : "즐겨찾기 추가"}
            title={isFav ? "즐겨찾기 해제" : "즐겨찾기 추가"}
            className="inline-flex min-h-10 min-w-10 shrink-0 items-center justify-center rounded-md border border-[var(--surface-border)] bg-[var(--surface-section)] transition-colors hover:bg-[var(--surface-section-hover)] disabled:opacity-50"
          >
            <Star
              size={18}
              className={isFav ? "fill-yellow-400 text-yellow-400" : ""}
            />
          </button>
          <button
            type="button"
            onClick={onToggleTheme}
            aria-label={themeMode === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환"}
            title={themeMode === "dark" ? "라이트 모드" : "다크 모드"}
            className="inline-flex min-h-10 min-w-10 shrink-0 items-center justify-center rounded-md border border-[var(--surface-border)] bg-[var(--surface-section)] transition-colors hover:bg-[var(--surface-section-hover)]"
          >
            {themeMode === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </div>

      {favoritesOpen ? (
        <div className="border-t border-[var(--surface-border)] bg-[var(--surface-bg)]/45 px-2 py-2">
          {favorites.length > 0 ? (
            <div className="flex gap-1.5 overflow-x-auto pb-1">
              {favorites.map((stock) => {
                const selected = stock.ticker.toUpperCase() === normalizedTicker;
                return (
                  <Link
                    key={stock.ticker}
                    href={`/stock/${stock.ticker}`}
                    className={`group min-w-[132px] rounded-md border px-2.5 py-2 transition-colors ${
                      selected
                        ? "border-blue-500/45 bg-blue-500/15 text-blue-700 dark:text-blue-300"
                        : "border-[var(--surface-border)] bg-[var(--surface-card)] hover:bg-[var(--surface-section-hover)]"
                    }`}
                    aria-current={selected ? "page" : undefined}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold">{stock.ticker}</span>
                      {selected ? (
                        <span className="rounded border border-blue-500/30 px-1.5 py-0.5 text-[10px] leading-none">
                          현재
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-0.5 truncate text-xs text-[var(--surface-text-muted)]">
                      {stock.name || stock.market}
                    </div>
                  </Link>
                );
              })}
            </div>
          ) : (
            <div className="flex items-center gap-2 rounded-md border border-dashed border-[var(--surface-border)] px-3 py-2 text-sm text-[var(--surface-text-muted)]">
              <UserRound size={16} />
              관심목록이 비어 있어요. 별표를 눌러 현재 종목을 추가할 수 있습니다.
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}

function PipelineStep({ icon, label }: { icon: ReactNode; label: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-blue-500/25 bg-blue-500/10 px-1.5 py-0.5">
      {icon}
      {label}
    </span>
  );
}

interface RefreshActionProps {
  icon: ReactNode;
  label: string;           // 모바일 button text (짧게: "전체" / "가격" / "뉴스" / "AI")
  fullLabel?: string;      // sm+ 에 보일 긴 text ("전체 새로고침" 등). 없으면 label 그대로.
  busyLabel: string;
  busy: boolean;
  disabled?: boolean;
  onClick: () => void | Promise<void>;
  timestamp: Date | null;
  timestampPrefix: string;
  cooldownLabel?: string | null;
  overrideSubtext?: string | null;
  now: number;
  tone: "neutral" | "info" | "warning" | "primary";
  title: string;
}

const TONE_CLASSES: Record<RefreshActionProps["tone"], string> = {
  neutral:
    "border border-[var(--surface-border)] bg-[var(--surface-card)] hover:bg-[var(--surface-section-hover)] text-[var(--surface-text)]",
  info: "border border-sky-500/40 bg-sky-500/10 hover:bg-sky-500/20 text-sky-700 dark:text-sky-300",
  warning:
    "border border-amber-500/40 bg-amber-500/10 hover:bg-amber-500/20 text-amber-700 dark:text-amber-300",
  primary:
    "border border-blue-500/50 bg-blue-500/10 hover:bg-blue-500/20 text-blue-700 dark:text-blue-300",
};

function RefreshAction({
  icon,
  label,
  fullLabel,
  busyLabel,
  busy,
  disabled,
  onClick,
  timestamp,
  timestampPrefix,
  cooldownLabel,
  overrideSubtext,
  now,
  tone,
  title,
}: RefreshActionProps) {
  const relative = formatKoRelative(timestamp, now);
  // 우선순위: overrideSubtext (action 직후 status) > cooldownLabel > timestamp.
  // overrideSubtext 는 짧게 (~7초) 표시되는 backend hint (예: "AI 의견 갱신 중").
  // timestampPrefix 빈 문자열이면 "데이터 없음" 라벨도 생략 (전체 새로고침처럼
  // 그 자체의 마지막 갱신 시각이 없는 케이스).
  const showFallback = timestamp != null || !!timestampPrefix;
  const subtext = overrideSubtext
    ? overrideSubtext
    : cooldownLabel
    ? cooldownLabel
    : timestamp
    ? `${timestampPrefix}: ${relative}`
    : showFallback
    ? `${timestampPrefix} 데이터 없음`
    : "";
  return (
    <div className="flex flex-col gap-1 min-w-0">
      <button
        type="button"
        onClick={onClick}
        disabled={busy || disabled}
        aria-label={fullLabel ?? label}
        title={title}
        className={`inline-flex items-center justify-center gap-1 sm:gap-1.5 rounded-md transition-colors px-2 sm:px-3 min-h-11 text-xs sm:text-sm disabled:opacity-50 disabled:cursor-not-allowed ${TONE_CLASSES[tone]}`}
      >
        {busy ? <RefreshCw size={16} className="animate-spin" /> : icon}
        <span className="truncate">
          {busy ? (
            busyLabel
          ) : fullLabel ? (
            <>
              <span className="sm:hidden">{label}</span>
              <span className="hidden sm:inline">{fullLabel}</span>
            </>
          ) : (
            label
          )}
        </span>
      </button>
      {subtext ? (
        <span
          className="text-[10px] sm:text-[11px] text-center text-[var(--surface-text-subtle)] truncate"
          title={timestamp ? timestamp.toLocaleString("ko-KR") : undefined}
        >
          {subtext}
        </span>
      ) : null}
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
