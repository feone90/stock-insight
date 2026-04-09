"use client";

import type { Stock } from "@/types/stock";
import { addFavorite, removeFavorite, syncStock } from "@/services/api";
import { useState } from "react";

interface Props {
  readonly stock: Stock;
  readonly onSyncComplete?: () => void;
}

export function StockHeader({ stock, onSyncComplete }: Props) {
  const [isFav, setIsFav] = useState(stock.is_favorite ?? false);
  const [syncing, setSyncing] = useState(false);

  const toggleFavorite = async () => {
    if (isFav) {
      await removeFavorite(stock.ticker);
    } else {
      await addFavorite(stock.ticker);
    }
    setIsFav(!isFav);
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const result = await syncStock(stock.ticker);
      const { synced, errors } = result;
      const summary = Object.entries(synced)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => `${k} ${v}건`)
        .join(", ");
      alert(
        `동기화 완료: ${summary || "변경 없음"}${
          errors.length > 0 ? `\n⚠️ ${errors.join("\n")}` : ""
        }`
      );
      onSyncComplete?.();
    } catch {
      alert("동기화 실패");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="flex items-center justify-between border-b border-slate-800 bg-slate-900 px-6 py-4">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-bold text-slate-50">{stock.name}</h1>
        <span className="text-sm text-slate-500">
          {stock.ticker} | {stock.market}
        </span>
        <button
          onClick={toggleFavorite}
          className="text-lg transition-transform hover:scale-110"
        >
          {isFav ? "⭐" : "☆"}
        </button>
        <button
          onClick={handleSync}
          disabled={syncing}
          className="ml-2 rounded-md border border-slate-700 bg-slate-800 px-3 py-1 text-xs text-slate-300 transition-colors hover:bg-slate-700 disabled:opacity-50"
        >
          {syncing ? "동기화 중..." : "동기화"}
        </button>
      </div>
      <div className="text-right">
        <div className="text-2xl font-bold text-slate-50">
          {stock.current_price.toLocaleString()}
          {stock.market === "KRX" ? "원" : "$"}
        </div>
        <div
          className={`text-sm font-medium ${
            stock.change_percent >= 0 ? "text-green-400" : "text-red-400"
          }`}
        >
          {stock.change_percent >= 0 ? "▲" : "▼"}{" "}
          {Math.abs(stock.change).toLocaleString()} (
          {stock.change_percent >= 0 ? "+" : ""}
          {stock.change_percent}%)
        </div>
      </div>
    </div>
  );
}
