"use client";

import type { Stock } from "@/types/stock";
import { addFavorite, removeFavorite, syncStock } from "@/services/api";
import { isAdmin } from "@/services/auth";
import { showToast } from "@/components/ui/toast";
import { useState } from "react";

interface Props {
  readonly stock: Stock;
  readonly onSyncComplete?: () => void;
}

export function StockHeader({ stock, onSyncComplete }: Props) {
  const [isFav, setIsFav] = useState(stock.is_favorite ?? false);
  const [syncing, setSyncing] = useState(false);

  const toggleFavorite = async () => {
    try {
      if (isFav) {
        await removeFavorite(stock.ticker);
      } else {
        await addFavorite(stock.ticker);
      }
      setIsFav(!isFav);
    } catch {
      showToast("즐겨찾기 변경 실패", "error");
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const result = await syncStock(stock.ticker);
      const { synced, errors } = result;
      const summary = Object.entries(synced)
        .filter(([, v]) => v)
        .map(([k, v]) => `${k} ${v}`)
        .join(", ");
      showToast(
        `동기화 완료: ${summary || "변경 없음"}`,
        errors.length > 0 ? "info" : "success"
      );
      if (errors.length > 0) {
        showToast(`경고: ${errors[0]}`, "error");
      }
      onSyncComplete?.();
    } catch {
      showToast("동기화 실패. 관리자 로그인이 필요합니다.", "error");
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
        {isAdmin() && (
          <button
            onClick={handleSync}
            disabled={syncing}
            className="ml-2 rounded-md border border-slate-700 bg-slate-800 px-3 py-1 text-xs text-slate-300 transition-colors hover:bg-slate-700 disabled:opacity-50"
          >
            {syncing ? "동기화 중..." : "동기화"}
          </button>
        )}
      </div>
      <div className="text-right">
        <div className="text-2xl font-bold text-slate-50">
          {stock.current_price?.toLocaleString()}
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
