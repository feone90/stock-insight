"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getFavorites } from "@/services/api";
import { onUserChanged } from "@/services/user";
import type { Stock } from "@/types/stock";

const RECOMMENDATIONS: { ticker: string; name: string; market: string; desc: string }[] = [
  { ticker: "005930", name: "삼성전자", market: "KOSPI", desc: "한국 대표 반도체" },
  { ticker: "000660", name: "SK하이닉스", market: "KOSPI", desc: "HBM 메모리 선두" },
  { ticker: "TSLA", name: "Tesla", market: "NASDAQ", desc: "AI · 전기차" },
];

export default function Home() {
  const [favorites, setFavorites] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const reload = () => {
      setLoading(true);
      getFavorites()
        .then(setFavorites)
        .catch(console.error)
        .finally(() => setLoading(false));
    };
    reload();
    return onUserChanged(reload);
  }, []);

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      {loading ? (
        <div className="text-slate-500">로딩 중...</div>
      ) : favorites.length === 0 ? (
        <EmptyState />
      ) : (
        <>
          <h1 className="mb-2 text-2xl font-bold">⭐ 즐겨찾기 종목</h1>
          <p className="mb-8 text-sm text-slate-400">
            관심 종목을 선택하여 분석을 확인하세요. ⌘K로 종목을 검색할 수 있습니다.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            {favorites.map((stock) => (
              <Link
                key={stock.ticker}
                href={`/stock/${stock.ticker}`}
                className="group rounded-lg border border-slate-800 bg-slate-900 p-4 transition-colors hover:border-slate-600"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-semibold text-slate-50 group-hover:text-blue-400 transition-colors">
                      {stock.name}
                    </div>
                    <div className="text-sm text-slate-500">
                      {stock.ticker} · {stock.market}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-semibold text-slate-50">
                      {stock.current_price.toLocaleString()}
                      {stock.market === "KRX" ? "원" : "$"}
                    </div>
                    <div
                      className={`text-sm ${
                        stock.change_percent >= 0
                          ? "text-red-400"
                          : "text-blue-400"
                      }`}
                    >
                      {stock.change_percent >= 0 ? "▲" : "▼"}{" "}
                      {Math.abs(stock.change).toLocaleString()} (
                      {stock.change_percent >= 0 ? "+" : ""}
                      {stock.change_percent}%)
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function EmptyState() {
  const [shortcut, setShortcut] = useState("Ctrl+K");

  useEffect(() => {
    const isMac =
      typeof navigator !== "undefined" &&
      /Mac|iPhone|iPad|iPod/i.test(
        // navigator.platform is deprecated but still works; fall back to UA.
        (navigator as Navigator & { userAgentData?: { platform?: string } })
          .userAgentData?.platform ||
          navigator.platform ||
          navigator.userAgent ||
          "",
      );
    setShortcut(isMac ? "⌘K" : "Ctrl+K");
  }, []);

  return (
    <div className="space-y-7">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-[var(--surface-text)]">
          처음 보시나요?
        </h1>
        <p className="mt-3 text-sm text-[var(--surface-text-muted)] leading-relaxed">
          <kbd className="inline-flex items-center gap-1 text-xs border border-[var(--surface-border)] rounded px-1.5 py-0.5 font-mono text-[var(--surface-text)]">
            {shortcut}
          </kbd>
          {"  "}로 종목을 검색하면 카드가 자동으로 생성됩니다. 아래 종목으로 빠르게 시작해보세요.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {RECOMMENDATIONS.map((s) => (
          <Link
            key={s.ticker}
            href={`/stock/${s.ticker}`}
            className="group rounded-xl border border-[var(--surface-border)] bg-[var(--surface-card)] p-4 transition-colors hover:border-blue-500/40"
          >
            <div className="font-semibold text-[var(--surface-text)] group-hover:text-blue-400 transition-colors">
              {s.name}
            </div>
            <div className="mt-1 text-xs font-mono text-[var(--surface-text-muted)]">
              {s.ticker} · {s.market}
            </div>
            <div className="mt-2 text-xs text-[var(--surface-text-muted)]">
              {s.desc}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
