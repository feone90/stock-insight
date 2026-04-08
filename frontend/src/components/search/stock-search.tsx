"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "@/components/ui/command";
import { searchStocks } from "@/services/api";
import type { Stock } from "@/types/stock";

export function StockSearch() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Stock[]>([]);
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
    if (query.length < 1) {
      setResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      const data = await searchStocks(query);
      setResults(data);
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  const handleSelect = (ticker: string) => {
    setOpen(false);
    setQuery("");
    router.push(`/stock/${ticker}`);
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
      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput
          placeholder="종목명 또는 티커를 입력하세요..."
          value={query}
          onValueChange={setQuery}
        />
        <CommandList>
          <CommandEmpty>검색 결과가 없습니다.</CommandEmpty>
          <CommandGroup heading="종목">
            {results.map((stock) => (
              <CommandItem
                key={stock.ticker}
                value={stock.ticker}
                onSelect={() => handleSelect(stock.ticker)}
              >
                <div className="flex items-center gap-3">
                  <span className="font-medium text-slate-50">
                    {stock.name}
                  </span>
                  <span className="text-sm text-slate-500">
                    {stock.ticker} · {stock.market}
                  </span>
                </div>
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </>
  );
}
