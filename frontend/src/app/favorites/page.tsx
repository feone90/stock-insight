"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { FolderKanban, Home, Search } from "lucide-react";
import { getFavorites } from "@/services/api";
import { getActiveUser, onUserChanged } from "@/services/user";
import { currencyMark, isKRMarket } from "@/lib/markets";
import type { Stock } from "@/types/stock";

const RECOMMENDATIONS: { ticker: string; name: string; market: string; desc: string }[] = [
  { ticker: "005930", name: "삼성전자", market: "KOSPI", desc: "한국 대표 반도체" },
  { ticker: "000660", name: "SK하이닉스", market: "KOSPI", desc: "HBM 메모리 선두" },
  { ticker: "TSLA", name: "Tesla", market: "NASDAQ", desc: "AI · 전기차" },
];

export default function FavoritesPage() {
  const [favorites, setFavorites] = useState<Stock[]>([]);
  const [activeUser, setActiveUserState] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const reload = () => {
      setLoading(true);
      setActiveUserState(getActiveUser());
      getFavorites()
        .then(setFavorites)
        .catch(console.error)
        .finally(() => setLoading(false));
    };
    reload();
    return onUserChanged(reload);
  }, []);

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 md:px-6 md:py-9">
      <header className="mb-5 flex flex-col gap-3 border-b border-slate-800 pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="inline-flex items-center gap-2 rounded border border-amber-500/25 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-200">
            <FolderKanban size={14} />
            개인 즐겨찾기
          </div>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight text-slate-50 md:text-3xl">
            {activeUser ? `${activeUser} 관심 종목` : "관심 종목"}
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-400">
            매일 보는 개인 화면입니다. 카드를 열면 차트, 뉴스/이슈, 관계망, AI 판단을 한 화면에서 확인합니다.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href="/portfolio"
            className="inline-flex w-fit items-center gap-2 rounded-md border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-sm font-medium text-blue-100 transition-colors hover:bg-blue-500/15"
          >
            <FolderKanban size={15} />
            포트폴리오 전체 흐름
          </Link>
          <Link
            href="/"
            className="inline-flex w-fit items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm font-medium text-slate-300 transition-colors hover:border-slate-500 hover:text-slate-100"
          >
            <Home size={15} />
            홈
          </Link>
        </div>
      </header>

      {loading ? (
        <div className="text-slate-500">로딩 중...</div>
      ) : favorites.length === 0 ? (
        <EmptyState />
      ) : (
        <section>
          <div className="grid gap-4 sm:grid-cols-2">
            {favorites.map((stock) => (
              <FavoriteStockCard key={stock.ticker} stock={stock} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function FavoriteStockCard({ stock }: { stock: Stock }) {
  const isUp = stock.change_percent >= 0;
  return (
    <Link
      href={`/stock/${stock.ticker}`}
      className="group rounded-lg border border-slate-800 bg-slate-900 p-4 transition-colors hover:border-slate-600"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-semibold text-slate-50 transition-colors group-hover:text-blue-400">
            {stock.name}
          </div>
          <div className="text-sm text-slate-500">
            {stock.ticker} · {stock.market}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="font-semibold text-slate-50">
            {isKRMarket(stock.market) ? (
              <>
                {stock.current_price.toLocaleString()}
                <span className="ml-0.5 text-xs">원</span>
              </>
            ) : (
              <>
                {currencyMark(stock.market)}
                {stock.current_price.toLocaleString()}
              </>
            )}
          </div>
          <div className={`text-sm ${isUp ? "text-red-400" : "text-blue-400"}`}>
            {isUp ? "▲" : "▼"} {Math.abs(stock.change).toLocaleString()} (
            {isUp ? "+" : ""}
            {stock.change_percent}%)
          </div>
        </div>
      </div>
    </Link>
  );
}

function EmptyState() {
  return (
    <div className="space-y-7">
      <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/45 p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
          <Search size={16} className="text-cyan-300" />
          관심 종목을 추가하세요
        </div>
        <p className="mt-3 text-sm leading-relaxed text-slate-400">
          상단 검색창에서 종목을 검색하면 개인 즐겨찾기와 분석 카드가 만들어집니다.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {RECOMMENDATIONS.map((s) => (
          <Link
            key={s.ticker}
            href={`/stock/${s.ticker}`}
            className="group rounded-xl border border-slate-800 bg-slate-900 p-4 transition-colors hover:border-blue-500/40"
          >
            <div className="font-semibold text-slate-50 transition-colors group-hover:text-blue-400">
              {s.name}
            </div>
            <div className="mt-1 font-mono text-xs text-slate-500">
              {s.ticker} · {s.market}
            </div>
            <div className="mt-2 text-xs text-slate-500">{s.desc}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
