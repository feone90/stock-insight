"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { searchStocks } from "@/services/api";
import type { Stock } from "@/types/stock";

export function StockSearch() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Stock[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 100);
    } else {
      setQuery("");
      setResults([]);
      setSelectedIndex(-1);
    }
  }, [open]);

  useEffect(() => {
    if (query.length < 1) {
      setResults([]);
      return;
    }
    let active = true;
    const timer = setTimeout(async () => {
      try {
        const data = await searchStocks(query);
        // effect cleanup 후 stale 응답은 무시 (race protection)
        if (active) {
          setResults(data);
          setSelectedIndex(findExactMatchIndex(data, query));
        }
      } catch (e) {
        console.error("search failed:", e);
      }
    }, 300);
    return () => {
      clearTimeout(timer);
      active = false;
    };
  }, [query]);

  const handleSelect = (ticker: string) => {
    setOpen(false);
    setQuery("");
    router.push(`/stock/${ticker}`);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.min(prev + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.max(prev - 1, 0));
    } else if (e.key === "Enter" && selectedIndex >= 0 && results[selectedIndex]) {
      handleSelect(results[selectedIndex].ticker);
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-400 hover:border-slate-600 transition-colors"
      >
        <span>🔍</span>
        <span>종목 검색...</span>
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          className="top-1/3 translate-y-0 overflow-hidden rounded-xl p-0 sm:max-w-md"
          showCloseButton={false}
        >
          <DialogHeader className="sr-only">
            <DialogTitle>종목 검색</DialogTitle>
            <DialogDescription>종목명 또는 티커를 입력하세요</DialogDescription>
          </DialogHeader>
          <div className="p-3 pb-0">
            <div className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2">
              <span className="text-slate-500">🔍</span>
              <input
                ref={inputRef}
                type="text"
                placeholder="종목명 또는 티커를 입력하세요..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                className="w-full bg-transparent text-sm text-slate-50 outline-none placeholder:text-slate-500"
              />
            </div>
          </div>
          <div className="max-h-72 overflow-y-auto p-2">
            {query.length > 0 && results.length === 0 && (
              <p className="py-6 text-center text-sm text-slate-500">
                검색 결과가 없습니다.
              </p>
            )}
            {results.map((stock, index) => (
              <button
                key={stock.ticker}
                onClick={() => handleSelect(stock.ticker)}
                className={`flex w-full items-start gap-3 rounded-lg px-3 py-2 text-left transition-colors ${
                  index === selectedIndex
                    ? "bg-slate-800 text-slate-50"
                    : "text-slate-300 hover:bg-slate-800/50"
                }`}
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{stock.name}</span>
                  <span className="mt-0.5 block truncate text-xs text-slate-500">
                    {stock.sector || "업종 정보 없음"}
                  </span>
                </span>
                <span className="shrink-0 text-right">
                  <span className="block font-mono text-xs text-slate-400">
                    {stock.ticker} · {stock.market}
                  </span>
                  <span className="mt-0.5 block text-xs text-slate-500">
                    {formatSearchPrice(stock)}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function findExactMatchIndex(results: Stock[], query: string): number {
  const q = query.trim().toUpperCase();
  if (!q) return -1;
  return results.findIndex(
    (stock) => stock.ticker.toUpperCase() === q || stock.name.toUpperCase() === q,
  );
}

function formatSearchPrice(stock: Stock): string {
  if (!stock.current_price) return "가격 대기";
  if (stock.market === "KOSPI" || stock.market === "KOSDAQ" || stock.market === "KRX") {
    return `${Math.round(stock.current_price).toLocaleString()}원`;
  }
  return `$${stock.current_price.toLocaleString()}`;
}
