import { ImageResponse } from "next/og";

/**
 * Dynamic OG image per stock — Next.js 16 file convention.
 *
 * 2026-05-19 — step 2 (대대적 layout) 500 error. step 2-a: 기존 step 1 layout
 * 그대로 유지하고 fetched data 만 주입 (큰 텍스트만 종목명으로). layout 자체
 * 문제인지 fetch 문제인지 격리.
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
  const displayName = meta?.name ?? ticker.toUpperCase();

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
          {displayName}
        </div>
        <div style={{ fontSize: 32, color: "#64748b", marginTop: 24 }}>
          종목 분석 카드
        </div>
      </div>
    ),
    {
      ...size,
      fonts: pretendard
        ? [
            {
              name: "Pretendard",
              data: pretendard,
              style: "normal",
              weight: 700,
            },
          ]
        : undefined,
    },
  );
}
