import { ImageResponse } from "next/og";

/**
 * Dynamic OG image per stock. Next.js 16 convention — same dir as page.tsx
 * with `opengraph-image.tsx` 가 자동 메타 `og:image` 와 `twitter:image` 로 연결.
 *
 * 2026-05-19 — 진짜 원인 격리 위해 minimal version 부터. backend fetch +
 * Pretendard font fetch 둘 다 제거. ticker 만 표시 + ASCII only. 일단 이게
 * generate 되는지 확인 후 부분씩 추가.
 */

export const alt = "StockInsight 종목 카드";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function OpengraphImage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;

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
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ fontSize: 48, color: "#94a3b8", marginBottom: 24 }}>
          StockInsight
        </div>
        <div style={{ fontSize: 120, fontWeight: 700, fontFamily: "monospace" }}>
          {ticker.toUpperCase()}
        </div>
        <div style={{ fontSize: 32, color: "#64748b", marginTop: 24 }}>
          stock card
        </div>
      </div>
    ),
    { ...size },
  );
}
