"use client";

import type { Stock } from "@/types/stock";
import { addFavorite, removeFavorite } from "@/services/api";
import { useState } from "react";

interface Props {
  stock: Stock;
}

export function StockHeader({ stock }: Props) {
  const [isFav, setIsFav] = useState(stock.is_favorite ?? false);

  const toggleFavorite = async () => {
    if (isFav) {
      await removeFavorite(stock.ticker);
    } else {
      await addFavorite(stock.ticker);
    }
    setIsFav(!isFav);
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
