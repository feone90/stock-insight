import { ImageResponse } from "next/og";

/**
 * Dynamic OG image per stock. Next.js 16 convention — same dir as page.tsx
 * with `opengraph-image.tsx` 가 자동 메타 `og:image` 와 `twitter:image` 로 연결.
 *
 * 2026-05-19 — minimal ASCII version 이 정상 generate 확인 (HTTP 200, 37KB).
 * Step 1: Pretendard font fetch + Korean static text 추가 (backend fetch 는 아직).
 */

export const alt = "StockInsight 종목 카드";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

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
  const pretendard = await loadPretendard();

  const fontFamily = pretendard ? "Pretendard" : "sans-serif";

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
        <div style={{ fontSize: 120, fontWeight: 700, fontFamily: "monospace" }}>
          {ticker.toUpperCase()}
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
