import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { TopNav } from "@/components/layout/top-nav";
import { ToastContainer } from "@/components/ui/toast";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// 2026-05-19 — metadataBase 는 *production URL* 가리켜야 함. 옛 코드는
// `VERCEL_URL` (deployment-specific hash URL) 사용 → preview 보호되면 카톡이
// og:image fetch 시 401 받아 이미지 안 보임. `VERCEL_PROJECT_PRODUCTION_URL`
// 은 항상 production alias (stock-insight-six.vercel.app) — public 접근 OK.
const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL ||
  (process.env.VERCEL_PROJECT_PRODUCTION_URL
    ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`
    : "https://stock-insight-six.vercel.app");

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "StockInsight — 주식 분석 대시보드",
    template: "%s | StockInsight",
  },
  description:
    "관계도 · 뉴스 · 정치 시그널 · AI 의견 · 최근 가격 분석 — 가족 친화 주식 분석 대시보드",
  openGraph: {
    title: "StockInsight — 주식 분석 대시보드",
    description:
      "관계도 · 뉴스 · 정치 시그널 · AI 의견 · 최근 가격 분석 — 가족 친화 주식 분석 대시보드",
    type: "website",
    locale: "ko_KR",
    siteName: "StockInsight",
  },
  twitter: {
    card: "summary_large_image",
    title: "StockInsight — 주식 분석 대시보드",
    description:
      "관계도 · 뉴스 · 정치 시그널 · AI 의견 · 최근 가격 분석",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ko"
      className={`${geistSans.variable} ${geistMono.variable} dark`}
    >
      <body className="bg-slate-950 text-slate-50 min-h-screen">
          <TopNav />
          <main>{children}</main>
          <ToastContainer />
        </body>
    </html>
  );
}
