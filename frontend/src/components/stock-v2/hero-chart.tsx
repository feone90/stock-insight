"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  CrosshairMode,
  LineSeries,
  LineStyle,
  type IChartApi,
  type LineData,
  type Time,
  createChart,
} from "lightweight-charts";
import { chartTokens, pick } from "@/lib/design-tokens";
import { useTheme } from "@/lib/use-theme";
import { getStockPrices } from "@/services/api";

/**
 * Hero chart — close line + MA20 dashed. Volume bars deferred to sub-phase E.
 *
 * Spec §3.1 layout. Plan §7.2 (reuse lightweight-charts setup) + §17.6 (mobile
 * 240px / desktop 320px). Theme-aware via `chartTokens`.
 */
export function HeroChart({
  ticker,
  days = 30,
}: {
  ticker: string;
  days?: number;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { mode } = useTheme();

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;

    let cancelled = false;
    let chart: IChartApi | null = null;
    let onResize: (() => void) | null = null;

    (async () => {
      let prices;
      try {
        prices = await getStockPrices(ticker, days);
      } catch {
        return; // Sub-phase E will surface fetch failures explicitly
      }
      if (cancelled || !node || prices.length === 0) return;

      const tokens = pick(chartTokens, mode);
      chart = createChart(node, {
        layout: {
          background: { type: ColorType.Solid, color: "transparent" },
          textColor: tokens.text,
        },
        grid: {
          vertLines: { color: tokens.grid },
          horzLines: { color: tokens.grid },
        },
        crosshair: { mode: CrosshairMode.Normal },
        // 한국어 날짜 표기 — 기본 영문 ("Apr 30 '26")을 "26년 4월 30일"로.
        localization: {
          locale: "ko-KR",
          dateFormat: "yy년 M월 d일",
        },
        // 시간축 라벨도 한국어 (월/일 단위 라벨러).
        timeScale: {
          tickMarkFormatter: (time: Time) => {
            const d = typeof time === "string" ? new Date(time) : new Date((time as number) * 1000);
            const month = d.getMonth() + 1;
            const day = d.getDate();
            return day === 1 ? `${month}월` : `${day}일`;
          },
        },
        width: node.clientWidth,
        height: window.innerWidth < 768 ? 240 : 320,
      });

      const closeSeries = chart.addSeries(LineSeries, {
        color: tokens.close,
        lineWidth: 2,
        priceLineVisible: false,
      });
      closeSeries.setData(
        prices.map((p) => ({ time: p.date as Time, value: p.close })),
      );

      if (prices.length >= 20) {
        const ma20Series = chart.addSeries(LineSeries, {
          color: tokens.ma20,
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          priceLineVisible: false,
        });
        const ma20: LineData<Time>[] = [];
        for (let i = 19; i < prices.length; i++) {
          const slice = prices.slice(i - 19, i + 1);
          const avg = slice.reduce((s, d) => s + d.close, 0) / 20;
          ma20.push({
            time: prices[i].date as Time,
            value: Math.round(avg * 100) / 100,
          });
        }
        ma20Series.setData(ma20);
      }

      chart.timeScale().fitContent();

      onResize = () => {
        if (chart && node) chart.applyOptions({ width: node.clientWidth });
      };
      window.addEventListener("resize", onResize);
    })();

    return () => {
      cancelled = true;
      if (onResize) window.removeEventListener("resize", onResize);
      chart?.remove();
    };
  }, [ticker, days, mode]);

  return <div ref={containerRef} className="w-full h-60 md:h-80" />;
}
