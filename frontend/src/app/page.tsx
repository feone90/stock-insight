"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getFavorites } from "@/services/api";
import { onUserChanged } from "@/services/user";
import type { Stock } from "@/types/stock";

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
      <h1 className="mb-2 text-2xl font-bold">⭐ 즐겨찾기 종목</h1>
      <p className="mb-8 text-sm text-slate-400">
        관심 종목을 선택하여 분석을 확인하세요. ⌘K로 종목을 검색할 수 있습니다.
      </p>

      {loading && <div className="text-slate-500">로딩 중...</div>}

      {!loading && favorites.length === 0 && (
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-8 text-center text-slate-400">
          즐겨찾기한 종목이 없습니다. 종목을 검색하여 추가해보세요.
        </div>
      )}

      {!loading && favorites.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {favorites.map((stock) => (
            <Link
              key={stock.ticker}
              href={`/v2/stock/${stock.ticker}`}
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
      )}
    </div>
  );
}
