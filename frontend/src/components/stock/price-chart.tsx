"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  type IChartApi,
  type CandlestickData,
  type LineData,
  type Time,
  ColorType,
  CrosshairMode,
  CandlestickSeries,
  LineSeries,
} from "lightweight-charts";
import type { PriceRecord } from "@/types/stock";

function calculateMA(data: PriceRecord[], period: number): LineData<Time>[] {
  const result: LineData<Time>[] = [];
  for (let i = period - 1; i < data.length; i++) {
    const slice = data.slice(i - period + 1, i + 1);
    const avg = slice.reduce((sum, d) => sum + d.close, 0) / period;
    result.push({ time: data[i].date as Time, value: Math.round(avg * 100) / 100 });
  }
  return result;
}

interface Props {
  prices: PriceRecord[];
  overlays: Record<string, boolean>;
  onCandleClick?: (date: string) => void;
}

export function PriceChart({ prices, overlays, onCandleClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || prices.length === 0) return;

    const chart: IChartApi = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0f172a" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "#1e293b" },
        horzLines: { color: "#1e293b" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      width: containerRef.current.clientWidth,
      height: 300,
    });

    // Candlestick series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderDownColor: "#ef4444",
      borderUpColor: "#22c55e",
      wickDownColor: "#ef4444",
      wickUpColor: "#22c55e",
    });
    const candleData: CandlestickData<Time>[] = prices.map((p) => ({
      time: p.date as Time,
      open: p.open,
      high: p.high,
      low: p.low,
      close: p.close,
    }));
    candleSeries.setData(candleData);

    // Close price line overlay
    if (overlays.closeLine) {
      const lineSeries = chart.addSeries(LineSeries, {
        color: "#60a5fa",
        lineWidth: 2,
        priceLineVisible: false,
      });
      const lineData: LineData<Time>[] = prices.map((p) => ({
        time: p.date as Time,
        value: p.close,
      }));
      lineSeries.setData(lineData);
    }

    // Moving average lines
    const maConfig = [
      { key: "ma5", period: 5, color: "#fbbf24" },
      { key: "ma20", period: 20, color: "#a78bfa" },
      { key: "ma60", period: 60, color: "#f472b6" },
    ];
    for (const ma of maConfig) {
      if (overlays[ma.key] && prices.length >= ma.period) {
        const maSeries = chart.addSeries(LineSeries, {
          color: ma.color,
          lineWidth: 1,
          priceLineVisible: false,
        });
        maSeries.setData(calculateMA(prices, ma.period));
      }
    }

    // Click handler
    chart.subscribeClick((param) => {
      if (param.time && onCandleClick) {
        onCandleClick(param.time as string);
      }
    });

    // Resize handler
    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);
    chart.timeScale().fitContent();

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [prices, overlays, onCandleClick]);

  return <div ref={containerRef} className="rounded-lg overflow-hidden" />;
}
