"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getStock, getStockPrices, getAnalysis } from "@/services/api";
import type { Stock, PriceRecord, Analysis, KeywordDetail } from "@/types/stock";
import { StockHeader } from "@/components/stock/stock-header";
import { PeriodTabs } from "@/components/stock/period-tabs";
import { PriceChart } from "@/components/stock/price-chart";
import { ChartToggles } from "@/components/stock/chart-toggles";
import { KeywordTimeline } from "@/components/stock/keyword-timeline";
import { KeywordSection } from "@/components/stock/keyword-section";
import { AiFeedback } from "@/components/stock/ai-feedback";
import { DetailPanel } from "@/components/stock/detail-panel";
import { StatsCard } from "@/components/stock/stats-card";

export default function StockDashboard() {
  const params = useParams();
  const ticker = params.ticker as string;

  const [stock, setStock] = useState<Stock | null>(null);
  const [prices, setPrices] = useState<PriceRecord[]>([]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [period, setPeriod] = useState("daily");
  const [loading, setLoading] = useState(true);

  const [overlays, setOverlays] = useState<Record<string, boolean>>({
    closeLine: true,
    ma5: false,
    ma20: true,
    ma60: false,
  });
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [selectedKeyword, setSelectedKeyword] = useState<KeywordDetail | null>(null);

  const periodToDays: Record<string, number> = {
    daily: 30,
    weekly: 90,
    monthly: 365,
    quarterly: 365,
    semi_annual: 730,
    annual: 1095,
  };

  useEffect(() => {
    setLoading(true);
    setSelectedKeyword(null);
    setSelectedDate(null);
    const days = periodToDays[period] ?? 90;
    Promise.all([
      getStock(ticker),
      getStockPrices(ticker, days),
      getAnalysis(ticker, period).catch(() => null),
    ])
      .then(([s, p, a]) => {
        setStock(s);
        setPrices(p);
        setAnalysis(a);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [ticker, period]);

  const handleToggle = (key: string) => {
    setOverlays((prev) => ({ ...prev, [key]: !prev[key] }));
  };

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
      <div className="border-b border-slate-800 bg-slate-900 px-6 py-3">
        <PeriodTabs selected={period} onSelect={setPeriod} />
      </div>

      <div className="flex min-h-[calc(100vh-180px)]">
        {/* Left Column */}
        <div className="flex-[2] border-r border-slate-800 p-6 space-y-4">
          <ChartToggles active={overlays} onToggle={handleToggle} />
          <PriceChart
            prices={prices}
            overlays={overlays}
            onCandleClick={setSelectedDate}
          />
          {analysis && (
            <>
              <KeywordTimeline
                dailyKeywords={analysis.daily_keywords}
                selectedDate={selectedDate}
                onDateSelect={setSelectedDate}
              />
              <KeywordSection
                keywords={analysis.keywords}
                selectedKeyword={selectedKeyword?.keyword ?? null}
                onSelect={setSelectedKeyword}
              />
              <AiFeedback
                summary={analysis.summary}
                feedback={analysis.feedback}
              />
            </>
          )}
        </div>

        {/* Right Column */}
        <div className="flex-1 bg-slate-950 p-6 space-y-4">
          <DetailPanel keyword={selectedKeyword} />
          {stock.stats && (
            <StatsCard stats={stock.stats} market={stock.market} />
          )}
        </div>
      </div>
    </div>
  );
}
