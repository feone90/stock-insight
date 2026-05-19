import { ImageResponse } from "next/og";

/**
 * Dynamic OG image per stock. Next.js 16 convention — same dir as page.tsx
 * with `opengraph-image.tsx` 가 자동 메타 `og:image` 와 `twitter:image` 로 연결.
 *
 * 2026-05-19 — 사용자 요청: 카톡/슬랙 URL 공유 시 종목명·가격·변동률이
 * 미리보기 카드 이미지로 즉시 보이게.
 *
 * Vercel Edge runtime + 자동 캐싱 (revalidate option 따라 분 단위). 카톡/슬랙
 * 자체도 미리보기 캐시 (수분~수일).
 */

// 2026-05-19 — runtime 명시 제거. Edge runtime 에서 이미지 생성 fail (curl
// 결과 200 + 0 bytes). Node.js runtime (Next.js 16 default) 가 ImageResponse
// 와 안정적. Vercel free tier 도 둘 다 지원.
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

// 2026-05-19 — Korean font 필수. Edge ImageResponse 기본 폰트가 한글 cover
// 안 해 처음 ship 시 Size=0 empty image 반환 (사용자가 "외국인 아저씨/집
// 사진" — 카톡이 fallback page screenshot 잡은 상태). Pretendard 한국
// product 인기 폰트 jsdelivr CDN.
async function loadKoreanFont(): Promise<ArrayBuffer | null> {
  try {
    const res = await fetch(
      "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/packages/pretendard/dist/web/static/woff/Pretendard-Bold.woff",
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

export default async function OpengraphImage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  const [meta, fontData] = await Promise.all([
    fetchStockMeta(ticker),
    loadKoreanFont(),
  ]);

  const name = meta?.name || ticker;
  const displayTicker = meta?.ticker || ticker;
  const market = meta?.market || "";
  const isKR = isKRMarket(market);
  const price = meta?.current_price ?? 0;
  const change = meta?.change ?? 0;
  const changePct = meta?.change_percent ?? 0;

  const sign = change >= 0 ? "+" : "";
  const priceStr = isKR
    ? `${price.toLocaleString()}원`
    : `$${price.toLocaleString()}`;

  // 한국 관습: 상승 = 빨강, 하락 = 파랑.
  const changeColor =
    change > 0 ? "#dc2626" : change < 0 ? "#2563eb" : "#94a3b8";

  return new ImageResponse(
    (
      <div
        style={{
          width: 1200,
          height: 630,
          background:
            "linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%)",
          color: "white",
          display: "flex",
          flexDirection: "column",
          padding: 80,
          justifyContent: "space-between",
          fontFamily: fontData ? "Pretendard" : "sans-serif",
        }}
      >
        {/* Top — Brand + market badge. 2026-05-19 emoji 제거 (Edge/Node
            ImageResponse 가 emoji 환경별 fail 가능). */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 16,
            fontSize: 32,
            color: "#cbd5e1",
          }}
        >
          <span style={{ fontWeight: 600 }}>StockInsight</span>
          {market ? (
            <span
              style={{
                marginLeft: 8,
                padding: "6px 16px",
                border: "1px solid #475569",
                borderRadius: 10,
                fontSize: 24,
                color: "#94a3b8",
              }}
            >
              {market}
            </span>
          ) : null}
        </div>

        {/* Middle — Name + ticker */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div
            style={{
              fontSize: name.length > 12 ? 84 : 108,
              fontWeight: 700,
              lineHeight: 1.05,
              letterSpacing: "-0.02em",
            }}
          >
            {name}
          </div>
          <div style={{ fontSize: 40, color: "#94a3b8", fontFamily: "monospace" }}>
            {displayTicker}
          </div>
        </div>

        {/* Bottom — Price + change + footer */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: 32,
              flexWrap: "wrap",
            }}
          >
            <div
              style={{
                fontSize: 96,
                fontWeight: 700,
                lineHeight: 1,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {priceStr}
            </div>
            <div
              style={{
                fontSize: 48,
                fontWeight: 600,
                color: changeColor,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {sign}
              {change.toLocaleString()} ({sign}
              {changePct.toFixed(2)}%)
            </div>
          </div>
          <div style={{ fontSize: 24, color: "#64748b" }}>
            관계도 / 뉴스 / 정치 시그널 / AI 의견 / 최근 가격 분석
          </div>
        </div>
      </div>
    ),
    {
      ...size,
      fonts: fontData
        ? [
            {
              name: "Pretendard",
              data: fontData,
              weight: 700,
              style: "normal",
            },
          ]
        : undefined,
    },
  );
}
