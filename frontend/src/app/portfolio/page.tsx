"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Clock3,
  LayoutDashboard,
  Layers3,
  Newspaper,
  RefreshCw,
  Signal,
  Sparkles,
} from "lucide-react";
import {
  getFavorites,
  getStockCard,
  getStockEventMarkers,
  getStockPrices,
  priceRefreshStock,
} from "@/services/api";
import { currencyMark, isKRMarket, isUSMarket } from "@/lib/markets";
import { onUserChanged } from "@/services/user";
import type { Stock, PriceRecord } from "@/types/stock";
import type { StockCard, StockEventMarker } from "@/types/card";

type PortfolioItem = {
  stock: Stock;
  card: StockCard | null;
  prices: PriceRecord[];
  events: StockEventMarker[];
  score: number;
  reason: string;
  priceTone: "positive" | "negative" | "neutral";
  driverTone: "positive" | "negative" | "mixed" | "neutral";
};

const STANCE_LABEL = {
  BUY: "매수 후보",
  WATCH: "관찰",
  REJECT: "보류",
} as const;

export default function PortfolioPage() {
  const [items, setItems] = useState<PortfolioItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshingPrices, setRefreshingPrices] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPortfolio = useCallback(async (options?: { quiet?: boolean }) => {
    if (!options?.quiet) setLoading(true);
    setError(null);
    try {
      const favorites = await getFavorites();
      const rows = await Promise.all(
        favorites.map(async (stock) => buildPortfolioItem(stock)),
      );
      setItems(rows.sort(comparePortfolioItems));
    } catch {
      setError("관심종목을 불러오지 못했습니다.");
    } finally {
      if (!options?.quiet) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let alive = true;

    const load = async () => {
      if (alive) {
        await loadPortfolio();
      }
    };

    load();
    const unsubscribe = onUserChanged(load);
    return () => {
      alive = false;
      unsubscribe();
    };
  }, [loadPortfolio]);

  const refreshPortfolioPrices = useCallback(async () => {
    if (refreshingPrices || items.length === 0) return;
    setRefreshingPrices(true);
    try {
      await Promise.allSettled(items.map((item) => priceRefreshStock(item.stock.ticker)));
      await new Promise((resolve) => setTimeout(resolve, 2500));
      await loadPortfolio({ quiet: true });
    } finally {
      setRefreshingPrices(false);
    }
  }, [items, loadPortfolio, refreshingPrices]);

  const leaders = useMemo(() => items.slice(0, 3), [items]);
  const stats = useMemo(() => summarize(items), [items]);

  return (
    <div className="mx-auto max-w-7xl px-4 py-5 md:px-6 md:py-8">
      <header className="mb-5 border-b border-slate-800 pb-5 md:mb-7 md:flex md:items-end md:justify-between">
        <div>
          <div className="inline-flex items-center gap-2 rounded border border-cyan-500/25 bg-cyan-500/10 px-2.5 py-1 text-xs font-medium text-cyan-200">
            <LayoutDashboard size={14} />
            포트폴리오
          </div>
          <h1 className="mt-3 text-[26px] font-semibold tracking-tight text-slate-50 md:text-4xl">
            오늘 먼저 볼 종목
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-400 md:text-[15px]">
            즐겨찾기 전체를 국내장 먼저, 이후 미국장 순서로 묶고 각 시장 안에서 오늘 가격 변동,
            AI 판단, 종합 요인, 뉴스와 관계 신호 기준으로 정렬했습니다.
          </p>
        </div>
        <div className="mt-4 flex flex-wrap gap-2 md:mt-0">
          <button
            type="button"
            onClick={refreshPortfolioPrices}
            disabled={refreshingPrices || loading || items.length === 0}
            className="inline-flex w-fit items-center gap-2 rounded-md border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-sm text-blue-100 transition-colors hover:border-blue-400/60 hover:bg-blue-500/15 disabled:cursor-not-allowed disabled:border-slate-800 disabled:bg-slate-900 disabled:text-slate-500"
          >
            <RefreshCw size={15} className={refreshingPrices ? "animate-spin" : ""} />
            {refreshingPrices ? "가격 갱신 중" : "가격 새로고침"}
          </button>
          <Link
            href="/"
            className="inline-flex w-fit items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-300 transition-colors hover:border-slate-500 hover:text-slate-100"
          >
            즐겨찾기 목록
            <ArrowRight size={15} />
          </Link>
        </div>
      </header>

      {loading ? (
        <PortfolioSkeleton />
      ) : error ? (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      ) : items.length === 0 ? (
        <EmptyPortfolio />
      ) : (
        <>
          <section className="mb-6 grid gap-4 md:grid-cols-[1.25fr_0.75fr]">
            <PriorityPanel leaders={leaders} />
            <MarketPulse stats={stats} />
          </section>

          <section className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
            {items.map((item) => (
              <PortfolioCard key={item.stock.ticker} item={item} />
            ))}
          </section>
        </>
      )}
    </div>
  );
}

async function buildPortfolioItem(stock: Stock): Promise<PortfolioItem> {
  const [cardResult, pricesResult, eventsResult] = await Promise.allSettled([
    getStockCard(stock.ticker),
    getStockPrices(stock.ticker, 60),
    getStockEventMarkers(stock.ticker, { days: 120, limit: 8 }),
  ]);
  const card = cardResult.status === "fulfilled" ? cardResult.value : null;
  const prices = pricesResult.status === "fulfilled" ? pricesResult.value : [];
  const events = eventsResult.status === "fulfilled" ? eventsResult.value.events : [];
  const latestEvent = events[0] ?? null;
  const score = importanceScore(stock, card, latestEvent);
  return {
    stock,
    card,
    prices,
    events,
    score,
    reason: pickReason(stock, card, latestEvent),
    priceTone: directionFromChange(stock.change_percent),
    driverTone: latestEvent?.direction ?? "neutral",
  };
}

function comparePortfolioItems(a: PortfolioItem, b: PortfolioItem): number {
  const marketDiff = marketOrder(a.stock.market) - marketOrder(b.stock.market);
  if (marketDiff !== 0) return marketDiff;
  return b.score - a.score;
}

function marketOrder(market: string): number {
  if (isKRMarket(market)) return 0;
  if (isUSMarket(market)) return 1;
  return 2;
}

function importanceScore(
  stock: Stock,
  card: StockCard | null,
  event: StockEventMarker | null,
): number {
  let score = Math.min(Math.abs(stock.change_percent) * 8, 45);
  if (event) {
    score += 18;
    if (event.confidence === "high") score += 12;
    if (event.direction === "negative") score += 8;
    if (event.direction === "mixed") score += 6;
  }
  if (card?.glance.stance === "BUY") score += 14;
  if (card?.glance.stance === "REJECT") score += 10;
  if ((card?.news.length ?? 0) >= 5) score += 8;
  if ((card?.relations.relations.length ?? 0) >= 5) score += 6;
  const biggestMove = Math.abs(card?.recent_price_move?.biggest_move_pct ?? 0);
  score += Math.min(biggestMove * 3, 18);
  return Math.round(score);
}

function pickReason(
  stock: Stock,
  card: StockCard | null,
  event: StockEventMarker | null,
): string {
  if (event?.keyword) return event.keyword;
  if (card?.recent_price_move?.one_line) return card.recent_price_move.one_line;
  if (card?.glance.one_line) return card.glance.one_line;
  if (Math.abs(stock.change_percent) >= 2) {
    return `${stock.change_percent >= 0 ? "상승" : "하락"} 변동률이 큽니다.`;
  }
  return "새 분석 신호를 기다리는 중입니다.";
}

function summarize(items: PortfolioItem[]) {
  const up = items.filter((item) => item.stock.change_percent > 0).length;
  const down = items.filter((item) => item.stock.change_percent < 0).length;
  const negativeDriverItems = items.filter((item) => item.driverTone === "negative");
  const negativeDrivers = negativeDriverItems.length;
  const cautionDrivers = negativeDriverItems.slice(0, 3).map((item) => ({
    ticker: item.stock.ticker,
    name: compactStockName(item.stock),
    reason: item.reason,
  }));
  const buy = items.filter((item) => item.card?.glance.stance === "BUY").length;
  const activeEvents = items.filter((item) => item.events.length > 0).length;
  return { up, down, negativeDrivers, cautionDrivers, buy, activeEvents, total: items.length };
}

function PriorityPanel({ leaders }: { leaders: PortfolioItem[] }) {
  return (
    <section className="min-w-0">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
          <Sparkles size={16} className="text-amber-300" />
          우선 확인
        </div>
        <span className="text-xs text-slate-500">국내 우선 · 중요도 Top 3</span>
      </div>
      <div className="grid gap-2 md:grid-cols-3">
        {leaders.map((item, index) => (
          <Link
            key={item.stock.ticker}
            href={`/stock/${item.stock.ticker}`}
            className={`group relative min-h-[132px] overflow-hidden rounded-lg border bg-slate-950/70 p-3 transition-colors hover:border-slate-500 ${toneBorder(item.priceTone)}`}
          >
            <div className={`absolute inset-x-0 top-0 h-0.5 ${toneBar(item.priceTone)}`} />
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="rounded border border-slate-700/80 px-1.5 py-0.5 text-[10px] text-slate-400">
                #{index + 1}
              </span>
              <PriceMovePill tone={item.priceTone} />
            </div>
            <div className="truncate text-sm font-semibold text-slate-50 group-hover:text-blue-300">
              {item.stock.name}
            </div>
            <div className="mt-0.5 font-mono text-xs text-slate-500">
              {item.stock.ticker} · {item.stock.market}
            </div>
            <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-slate-400">
              {item.reason}
            </p>
          </Link>
        ))}
      </div>
    </section>
  );
}

function MarketPulse({ stats }: { stats: ReturnType<typeof summarize> }) {
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-100">
        <Signal size={16} className="text-cyan-300" />
        전체 맥박
      </div>
      <div className="grid grid-cols-4 divide-x divide-slate-800 rounded border border-slate-800">
        <PulseTile label="상승" value={stats.up} tone="positive" />
        <PulseTile label="하락" value={stats.down} tone="negative" />
        <PulseTile label="매수" value={stats.buy} tone="positive" />
        <PulseTile label="요인" value={`${stats.activeEvents}/${stats.total}`} tone="neutral" />
      </div>
      <div className="mt-3 border-l-2 border-amber-400/70 bg-amber-400/10 px-3 py-2 text-xs leading-relaxed text-amber-100">
        <div className="font-medium text-amber-50">
          가격 방향: 상승 {stats.up}개 · 하락 {stats.down}개
        </div>
        {stats.cautionDrivers.length > 0 ? (
          <div className="mt-1.5">
            주의 요인:{" "}
            {stats.cautionDrivers.map((item, index) => (
              <span key={item.ticker}>
                {index > 0 ? " / " : ""}
                {item.name} - {item.reason}
              </span>
            ))}
            {stats.negativeDrivers > stats.cautionDrivers.length
              ? ` 외 ${stats.negativeDrivers - stats.cautionDrivers.length}개`
              : ""}
          </div>
        ) : (
          <div className="mt-1.5">주의 요인으로 따로 잡힌 종목은 없습니다.</div>
        )}
      </div>
    </section>
  );
}

function PulseTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone: "positive" | "negative" | "neutral";
}) {
  const cls =
    tone === "positive"
      ? "text-red-300"
      : tone === "negative"
        ? "text-blue-300"
        : "text-slate-200";
  return (
    <div className="px-2.5 py-2.5">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className={`mt-1 text-lg font-semibold ${cls}`}>{value}</div>
    </div>
  );
}

function PortfolioCard({ item }: { item: PortfolioItem }) {
  const { stock, card, prices, events } = item;
  const latestEvent = events[0] ?? null;
  const stance = card?.glance.stance;
  const relationCount = card?.relations.relations.length ?? 0;
  const newsCount = card?.news.length ?? 0;

  return (
    <Link
      href={`/stock/${stock.ticker}`}
      className={`group flex min-h-[306px] flex-col overflow-hidden rounded-lg border bg-slate-900/80 p-4 transition-colors hover:border-slate-500 ${toneBorder(item.priceTone)}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-base font-semibold text-slate-50 group-hover:text-blue-300">
            {stock.name}
          </div>
          <div className="mt-1 font-mono text-xs text-slate-500">
            {stock.ticker} · {stock.market}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="text-sm font-semibold text-slate-50">
            {formatPrice(stock)}
          </div>
          <div className={changeClass(stock.change_percent)}>
            {stock.change_percent >= 0 ? "▲" : "▼"} {Math.abs(stock.change_percent).toFixed(2)}%
          </div>
        </div>
      </div>

      <div className="mt-3 border-y border-slate-800 py-2">
        <Sparkline prices={prices} positive={stock.change_percent >= 0} />
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {stance ? <Badge tone={stanceTone(stance)}>{STANCE_LABEL[stance]}</Badge> : null}
        {card?.glance.final_grade ? <Badge tone="neutral">등급 {card.glance.final_grade}</Badge> : null}
        <PriceMovePill tone={item.priceTone} />
        {latestEvent ? <DriverPill tone={latestEvent.direction} /> : <Badge tone="neutral">요인 대기</Badge>}
      </div>

      <div className={`mt-3 border-l-2 px-3 py-1.5 ${toneLeftBorder(item.priceTone)}`}>
        <div className="mb-1 flex items-center gap-1.5 text-[11px] text-slate-500">
          <Activity size={13} />
          오늘 먼저 볼 신호
        </div>
        <p className="line-clamp-2 text-sm font-medium leading-relaxed text-slate-100">
          {item.reason}
        </p>
        {latestEvent?.summary ? (
          <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-slate-500">
            {latestEvent.summary}
          </p>
        ) : null}
      </div>

      <div className="mt-auto grid grid-cols-3 divide-x divide-slate-800 border-t border-slate-800 pt-3">
        <MiniMetric icon={<Newspaper size={13} />} label="뉴스" value={`${newsCount}건`} />
        <MiniMetric icon={<Layers3 size={13} />} label="관계" value={`${relationCount}개`} />
        <MiniMetric
          icon={<Clock3 size={13} />}
          label="분석"
          value={formatShortDate(card?.generated_at)}
        />
      </div>
    </Link>
  );
}

function Sparkline({
  prices,
  positive,
}: {
  prices: PriceRecord[];
  positive: boolean;
}) {
  const data = prices
    .slice()
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(-45);
  if (data.length < 2) {
    return (
      <div className="flex h-14 items-center justify-center text-xs text-slate-600">
        차트 데이터 대기
      </div>
    );
  }
  const closes = data.map((p) => p.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const points = closes.map((close, index) => {
    const x = (index / (closes.length - 1)) * 160;
    const y = 52 - ((close - min) / range) * 46;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const color = positive ? "#f87171" : "#60a5fa";
  return (
    <svg viewBox="0 0 160 56" className="h-14 w-full" role="img" aria-label="최근 가격 흐름">
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle
        cx={points.at(-1)?.split(",")[0] ?? 160}
        cy={points.at(-1)?.split(",")[1] ?? 28}
        r="2.5"
        fill={color}
      />
    </svg>
  );
}

function MiniMetric({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="px-2 first:pl-0 last:pr-0">
      <div className="flex items-center gap-1 text-[10px] text-slate-500">
        {icon}
        {label}
      </div>
      <div className="mt-1 truncate text-xs font-medium text-slate-200">{value}</div>
    </div>
  );
}

function PriceMovePill({ tone }: { tone: PortfolioItem["priceTone"] }) {
  if (tone === "positive") return <Badge tone="positive">오늘 상승</Badge>;
  if (tone === "negative") return <Badge tone="negative">오늘 하락</Badge>;
  return <Badge tone="neutral">보합</Badge>;
}

function DriverPill({ tone }: { tone: PortfolioItem["driverTone"] }) {
  if (tone === "positive") return <Badge tone="positive">호재 요인</Badge>;
  if (tone === "negative") return <Badge tone="negative">악재 요인</Badge>;
  if (tone === "mixed") return <Badge tone="mixed">요인 혼재</Badge>;
  return <Badge tone="neutral">중립 요인</Badge>;
}

function Badge({
  tone,
  children,
}: {
  tone: "positive" | "negative" | "mixed" | "neutral";
  children: ReactNode;
}) {
  const cls =
    tone === "positive"
      ? "border-red-500/30 bg-red-500/10 text-red-200"
      : tone === "negative"
        ? "border-blue-500/30 bg-blue-500/10 text-blue-200"
        : tone === "mixed"
          ? "border-amber-500/30 bg-amber-500/10 text-amber-200"
          : "border-slate-700 bg-slate-900 text-slate-300";
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${cls}`}>
      {children}
    </span>
  );
}

function PortfolioSkeleton() {
  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-[1.2fr_0.8fr]">
        <div className="h-44 animate-pulse rounded-lg bg-slate-900" />
        <div className="h-44 animate-pulse rounded-lg bg-slate-900" />
      </div>
      <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="h-72 animate-pulse rounded-lg bg-slate-900" />
        ))}
      </div>
    </div>
  );
}

function EmptyPortfolio() {
  return (
    <div className="rounded-lg border border-dashed border-slate-700 bg-slate-900/60 px-4 py-10 text-center">
      <BarChart3 className="mx-auto mb-3 text-slate-500" size={28} />
      <div className="text-base font-semibold text-slate-100">관심종목이 없습니다</div>
      <p className="mt-2 text-sm text-slate-500">
        종목을 즐겨찾기에 추가하면 이 페이지에서 전체 흐름을 한 번에 볼 수 있습니다.
      </p>
    </div>
  );
}

function formatPrice(stock: Stock): string {
  if (isKRMarket(stock.market)) return `${stock.current_price.toLocaleString()}원`;
  return `${currencyMark(stock.market)}${stock.current_price.toLocaleString()}`;
}

function compactStockName(stock: Stock): string {
  return stock.name || stock.ticker;
}

function formatShortDate(value?: string | null): string {
  if (!value) return "대기";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "완료";
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function directionFromChange(change: number): PortfolioItem["priceTone"] {
  if (change > 0) return "positive";
  if (change < 0) return "negative";
  return "neutral";
}

function stanceTone(stance: StockCard["glance"]["stance"]): "positive" | "negative" | "mixed" {
  if (stance === "BUY") return "positive";
  if (stance === "REJECT") return "negative";
  return "mixed";
}

function changeClass(change: number): string {
  return `mt-1 text-xs font-medium ${change >= 0 ? "text-red-300" : "text-blue-300"}`;
}

function toneBorder(tone: PortfolioItem["priceTone"] | PortfolioItem["driverTone"]): string {
  if (tone === "positive") return "border-red-500/25";
  if (tone === "negative") return "border-blue-500/30";
  if (tone === "mixed") return "border-amber-500/30";
  return "border-slate-800";
}

function toneBar(tone: PortfolioItem["priceTone"] | PortfolioItem["driverTone"]): string {
  if (tone === "positive") return "bg-red-400";
  if (tone === "negative") return "bg-blue-400";
  if (tone === "mixed") return "bg-amber-400";
  return "bg-slate-600";
}

function toneLeftBorder(tone: PortfolioItem["priceTone"] | PortfolioItem["driverTone"]): string {
  if (tone === "positive") return "border-red-400/70";
  if (tone === "negative") return "border-blue-400/70";
  if (tone === "mixed") return "border-amber-400/70";
  return "border-slate-600";
}
