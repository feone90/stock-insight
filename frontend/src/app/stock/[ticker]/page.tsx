"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getStock, getStockPrices, getAnalysis } from "@/services/api";
import type { Stock, PriceRecord, Analysis } from "@/types/stock";
import { StockHeader } from "@/components/stock/stock-header";
import { PeriodTabs } from "@/components/stock/period-tabs";

export default function StockDashboard() {
  const params = useParams();
  const ticker = params.ticker as string;

  const [stock, setStock] = useState<Stock | null>(null);
  const [prices, setPrices] = useState<PriceRecord[]>([]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [period, setPeriod] = useState("weekly");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([getStock(ticker), getStockPrices(ticker), getAnalysis(ticker, period)])
      .then(([s, p, a]) => {
        setStock(s);
        setPrices(p);
        setAnalysis(a);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [ticker, period]);

  if (loading || !stock) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-500">
        로딩 중...
      </div>
    );
  }

  return (
    <div>
      <StockHeader stock={stock} />
      <div className="px-6 py-3 border-b border-slate-800 bg-slate-900">
        <PeriodTabs selected={period} onSelect={setPeriod} />
      </div>
      <div className="flex">
        {/* Left: Chart + Keywords */}
        <div className="flex-[2] border-r border-slate-800 p-6">
          <div className="rounded-lg bg-slate-900 p-4 mb-4 h-[300px] flex items-center justify-center text-slate-500">
            차트 영역 (Task 8에서 구현)
          </div>
          <div className="text-slate-500 text-sm">
            키워드 영역 (Task 9에서 구현)
          </div>
        </div>
        {/* Right: Detail Panel */}
        <div className="flex-1 bg-slate-950 p-6">
          <div className="text-slate-500 text-sm">
            상세 패널 (Task 10에서 구현)
          </div>
        </div>
      </div>
    </div>
  );
}
