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
import { searchStocks, registerStock } from "@/services/api";
import type { Stock } from "@/types/stock";

export function StockSearch() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Stock[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
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
      setSelectedIndex(0);
    }
  }, [open]);

  useEffect(() => {
    if (query.length < 1) {
      setResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      const data = await searchStocks(query);
      setResults(data);
      setSelectedIndex(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  const handleSelect = async (ticker: string) => {
    setOpen(false);
    setQuery("");
    // DB에 없는 종목이면 자동 등록
    try {
      await registerStock(ticker);
    } catch {
      // 이미 등록되어 있거나 실패해도 페이지 이동은 시도
    }
    router.push(`/stock/${ticker}`);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.min(prev + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.max(prev - 1, 0));
    } else if (e.key === "Enter" && results[selectedIndex]) {
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
        <kbd className="ml-2 rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-500">
          ⌘K
        </kbd>
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
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors ${
                  index === selectedIndex
                    ? "bg-slate-800 text-slate-50"
                    : "text-slate-300 hover:bg-slate-800/50"
                }`}
              >
                <span className="font-medium">{stock.name}</span>
                <span className="text-sm text-slate-500">
                  {stock.ticker} · {stock.market}
                </span>
              </button>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
