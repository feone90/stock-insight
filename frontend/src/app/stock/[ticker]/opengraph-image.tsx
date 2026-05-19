import { ImageResponse } from "next/og";

/**
 * Dynamic OG image per stock — Next.js 16 file convention.
 *
 * 2026-05-19 — step 2-b: 3-section 풀 레이아웃 복원. step 2 (대대적) → 500
 * 였던 원인 가설: JSX 텍스트 mixing (`{a} · {b}`) 이 Satori 에서 multi-child
 * 로 인식되어 비-flex div fail. → 모든 텍스트 단일 string 으로 concat.
 */

export const alt = "StockInsight 종목 카드";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

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
    const res = await fetch(`${API_BASE}/api/stocks/${ticker}`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) return null;
    return (await res.json()) as StockMeta;
  } catch {
    return null;
  }
}

async function loadPretendard(): Promise<ArrayBuffer | null> {
  try {
    const res = await fetch(
      "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/packages/pretendard/dist/public/static/Pretendard-Bold.otf",
    );
    if (!res.ok) return null;
    return await res.arrayBuffer();
  } catch {
    return null;
  }
}

function isKRMarket(market: string): boolean {
  return market === "KOSPI" || market === "KOSDAQ";
}

function formatPrice(price: number, market: string): string {
  if (isKRMarket(market)) return `₩${price.toLocaleString()}`;
  return `$${price.toLocaleString()}`;
}

export default async function OpengraphImage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  const [meta, pretendard] = await Promise.all([
    fetchStockMeta(ticker),
    loadPretendard(),
  ]);

  const fontFamily = pretendard ? "Pretendard" : "sans-serif";
  const fonts = pretendard
    ? [{ name: "Pretendard", data: pretendard, style: "normal" as const, weight: 700 as const }]
    : undefined;

  // Fallback when backend unreachable — show ticker + brand only
  if (!meta) {
    return new ImageResponse(
      (
        <div
          style={{
            width: 1200,
            height: 630,
            background: "#0f172a",
            color: "white",
            display: "flex",
            flexDirection: "column",
            padding: 80,
            justifyContent: "center",
            alignItems: "center",
            fontFamily,
          }}
        >
          <div style={{ fontSize: 48, color: "#94a3b8", marginBottom: 24 }}>
            StockInsight
          </div>
          <div style={{ fontSize: 120, fontWeight: 700 }}>
            {ticker.toUpperCase()}
          </div>
          <div style={{ fontSize: 32, color: "#64748b", marginTop: 24 }}>
            종목 분석 카드
          </div>
        </div>
      ),
      { ...size, fonts },
    );
  }

  const isUp = meta.change >= 0;
  const changeColor = isUp ? "#ef4444" : "#3b82f6"; // KR convention: 빨강=상승, 파랑=하락
  const sign = isUp ? "+" : "";
  const priceStr = formatPrice(meta.current_price, meta.market);
  const changeStr = `${sign}${meta.change.toLocaleString()} (${sign}${meta.change_percent.toFixed(2)}%)`;
  const tickerLine = `${meta.ticker} · ${meta.market}`;

  return new ImageResponse(
    (
      <div
        style={{
          width: 1200,
          height: 630,
          background: "#0f172a",
          color: "white",
          display: "flex",
          flexDirection: "column",
          padding: 80,
          justifyContent: "space-between",
          fontFamily,
        }}
      >
        {/* Header: brand */}
        <div style={{ fontSize: 36, color: "#94a3b8", fontWeight: 700 }}>
          StockInsight
        </div>

        {/* Body: stock name + ticker · market */}
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ fontSize: 96, fontWeight: 700, marginBottom: 16 }}>
            {meta.name}
          </div>
          <div style={{ fontSize: 32, color: "#94a3b8" }}>
            {tickerLine}
          </div>
        </div>

        {/* Footer: price + change */}
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ fontSize: 88, fontWeight: 700, marginBottom: 12 }}>
            {priceStr}
          </div>
          <div style={{ fontSize: 40, color: changeColor, fontWeight: 700 }}>
            {changeStr}
          </div>
        </div>
      </div>
    ),
    { ...size, fonts },
  );
}
