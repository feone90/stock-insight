import type { Metadata } from "next";
import { StockPageClient } from "./StockPageClient";
import { safeDecodeRouteParam } from "@/lib/stock-route";

/**
 * Stock card page — canonical route + dynamic metadata for URL sharing.
 *
 * 2026-05-19 — `useParams` 클라이언트 wrapper 를 `StockPageClient` 로 분리하고,
 * 이 파일을 server component 화. `generateMetadata` 가 종목별 title /
 * description / openGraph 메타 동적으로 생성 → 카톡/슬랙/트위터 공유 시
 * 종목명·가격·변동률이 미리보기에 자동 표시 (opengraph-image.tsx 와 결합).
 */

interface StockMeta {
  name: string;
  ticker: string;
  market: string;
  current_price: number;
  change: number;
  change_percent: number;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchStockMeta(ticker: string): Promise<StockMeta | null> {
  try {
    const res = await fetch(`${API_BASE}/api/stocks/${encodeURIComponent(ticker)}`, {
      // 60s ISR — OG 미리보기는 카카오/슬랙 등이 자체 캐시 (수분~수일) 하므로
      // 분 단위 정확도 불필요. 백엔드 부담 ↓.
      next: { revalidate: 60 },
    });
    if (!res.ok) return null;
    return (await res.json()) as StockMeta;
  } catch {
    return null;
  }
}

function isKRMarket(market: string): boolean {
  return market === "KOSPI" || market === "KOSDAQ";
}

function formatPrice(price: number, market: string): string {
  if (isKRMarket(market)) return `${price.toLocaleString()}원`;
  return `$${price.toLocaleString()}`;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ ticker: string }>;
}): Promise<Metadata> {
  const { ticker: rawTicker } = await params;
  const ticker = safeDecodeRouteParam(rawTicker);
  const meta = await fetchStockMeta(ticker);

  if (!meta) {
    return {
      title: `${ticker} — StockInsight`,
      description: "주식 분석 카드 — 관계도 · 뉴스 · AI 의견",
    };
  }

  const sign = meta.change >= 0 ? "+" : "";
  const pct = `${sign}${meta.change_percent.toFixed(2)}%`;
  const priceStr = formatPrice(meta.current_price, meta.market);
  const title = `${meta.name} ${priceStr} (${pct}) — StockInsight`;
  const description = `${meta.name} (${meta.ticker}) — 관계도, 뉴스, AI 의견, 최근 가격 움직임 분석`;

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      type: "website",
      locale: "ko_KR",
      siteName: "StockInsight",
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
    },
  };
}

export default async function StockPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker: rawTicker } = await params;
  const ticker = safeDecodeRouteParam(rawTicker);
  return <StockPageClient ticker={ticker} />;
}
