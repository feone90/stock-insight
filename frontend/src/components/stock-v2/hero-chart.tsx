"use client";

import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  LineSeries,
  LineStyle,
  createSeriesMarkers,
  type CandlestickData,
  type IChartApi,
  type LineData,
  type SeriesMarker,
  type Time,
  createChart,
} from "lightweight-charts";
import { chartTokens, pick } from "@/lib/design-tokens";
import { useTheme } from "@/lib/use-theme";
import { getStockEventMarkers, getStockPrices } from "@/services/api";
import type { EventDirection, EventSourceType, StockEventMarker } from "@/types/card";

/**
 * Hero chart — 캔들 (상승=emerald, 하락=rose) + MA20 (옅은 점선).
 * Plan §7.2 + §17.6 (mobile 240px / desktop 320px). 다크/라이트 토큰 인지.
 */
const PERIOD_OPTIONS: Array<{ label: string; days: number }> = [
  { label: "10일", days: 10 },
  { label: "30일", days: 30 },
  { label: "60일", days: 60 },
  { label: "3개월", days: 90 },
  { label: "6개월", days: 180 },
  { label: "1년", days: 365 },
];

export function HeroChart({
  ticker,
  days: initialDays = 60,
  priceAsof,
}: {
  ticker: string;
  days?: number;
  /**
   * 2026-05-18 — 카드의 price_asof 가 advance 하면 chart 도 re-fetch.
   * 옛 코드는 mount 1회만 fetch — 가격 새로고침 후 차트는 stale.
   */
  priceAsof?: string | null;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { mode } = useTheme();
  const [days, setDays] = useState(initialDays);
  const [events, setEvents] = useState<StockEventMarker[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;

    let cancelled = false;
    let chart: IChartApi | null = null;
    let onResize: (() => void) | null = null;
    let onClick: ((param: { hoveredObjectId?: unknown; time?: Time }) => void) | null = null;

    (async () => {
      let prices;
      let markerEvents: StockEventMarker[] = [];
      try {
        const [priceRows, eventRows] = await Promise.all([
          getStockPrices(ticker, days),
          getStockEventMarkers(ticker, { days, limit: 40 }).catch(() => ({ events: [] })),
        ]);
        prices = priceRows;
        markerEvents = eventRows.events;
      } catch {
        return;
      }
      if (cancelled || !node || prices.length === 0) return;
      const chartEvents = selectChartEvents(markerEvents);
      setEvents(markerEvents);

      // PriceHistory는 desc일 수도 — 캔들은 ascending 시간 필요.
      const sorted = [...prices].sort((a, b) => a.date.localeCompare(b.date));

      const tokens = pick(chartTokens, mode);
      const isDark = mode === "dark";
      const upColor = isDark ? "#f87171" : "#dc2626"; // 한국 관습: 상승=빨강 (red 400/600)
      const downColor = isDark ? "#60a5fa" : "#2563eb"; // 한국 관습: 하락=파랑 (blue 400/600)
      const ma20Color = isDark
        ? "rgba(148, 163, 184, 0.55)"
        : "rgba(100, 116, 139, 0.45)";

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
        // 모든 시간 표시(축 + tooltip + crosshair) 한국어 통일.
        localization: {
          locale: "ko-KR",
          timeFormatter: (t: Time) => formatKoreanDate(t, true),
        },
        timeScale: {
          tickMarkFormatter: (t: Time) => formatTickKorean(t),
          rightOffset: 5,
          barSpacing: 8,
        },
        width: node.clientWidth,
        height: window.innerWidth < 768 ? 260 : 340,
      });

      // 메인 캔들 시리즈 — 상승/하락 한눈에.
      const candle = chart.addSeries(CandlestickSeries, {
        upColor,
        downColor,
        borderUpColor: upColor,
        borderDownColor: downColor,
        wickUpColor: upColor,
        wickDownColor: downColor,
        priceLineVisible: true,
        priceLineWidth: 1,
        priceLineStyle: LineStyle.Dotted,
      });
      candle.setData(
        sorted.map<CandlestickData<Time>>((p) => ({
          time: p.date as Time,
          open: p.open,
          high: p.high,
          low: p.low,
          close: p.close,
        })),
      );
      createSeriesMarkers(
        candle,
        chartEvents
          .sort((a, b) => a.date.localeCompare(b.date))
          .map<SeriesMarker<Time>>((event) => ({
            id: event.id,
            time: event.date as Time,
            position: markerPosition(event.direction),
            shape: markerShape(event.direction),
            color: markerColor(event.direction, mode),
          })),
        { zOrder: "top" },
      );
      onClick = (param) => {
        const objectId = typeof param.hoveredObjectId === "string" ? param.hoveredObjectId : null;
        const eventFromMarker = objectId
          ? chartEvents.find((event) => event.id === objectId)
          : null;
        const dateFromClick = eventFromMarker?.date ?? (param.time ? timeToDateString(param.time) : null);
        if (!dateFromClick) return;
        const hasEvents = markerEvents.some((event) => event.date === dateFromClick);
        if (hasEvents) setSelectedDate(dateFromClick);
      };
      chart.subscribeClick(onClick);

      // MA20 — 옅은 회색 점선. 단기·장기 추세 비교용 (정배열/역배열).
      if (sorted.length >= 20) {
        const ma20Series = chart.addSeries(LineSeries, {
          color: ma20Color,
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        const ma20: LineData<Time>[] = [];
        for (let i = 19; i < sorted.length; i++) {
          const slice = sorted.slice(i - 19, i + 1);
          const avg = slice.reduce((s, d) => s + d.close, 0) / 20;
          ma20.push({
            time: sorted[i].date as Time,
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
      if (onClick) chart?.unsubscribeClick(onClick);
      chart?.remove();
    };
  }, [ticker, days, mode, priceAsof]);

  const selectedEvents = selectedDate
    ? events.filter((event) => event.date === selectedDate)
    : [];

  return (
    <div className="relative">
      <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-3 text-[11px] text-[var(--surface-text-muted)]">
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-2 h-3 bg-red-500 dark:bg-red-400" />
            상승
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-2 h-3 bg-blue-500 dark:bg-blue-400" />
            하락
          </span>
          <span
            className="flex items-center gap-1.5"
            title="20일 평균 가격. 현재가(캔들)가 점선 위면 단기 추세 우상향, 아래면 약세."
          >
            <span
              className="inline-block w-3 h-0 border-t border-dashed"
              style={{ borderColor: "var(--surface-text-muted)" }}
            />
            20일 평균
          </span>
          <span
            className="flex items-center gap-1.5"
            title="차트에는 날짜별 대표 이벤트 위치만 표시하고, 자세한 이유는 아래 이벤트 카드에서 확인합니다."
          >
            <span className="inline-flex h-3 w-3 items-center justify-center rounded-full border border-[var(--surface-text-muted)] text-[8px] leading-none">
              !
            </span>
            이벤트
          </span>
        </div>
        <div className="flex w-full items-center gap-1 overflow-x-auto rounded-md border border-[var(--surface-border)] bg-[var(--surface-card)] p-0.5 sm:w-auto">
          {PERIOD_OPTIONS.map((opt) => (
            <button
              key={opt.days}
              type="button"
              onClick={() => setDays(opt.days)}
              className={`shrink-0 px-2 py-1 rounded text-[11px] transition-colors ${
                days === opt.days
                  ? "bg-blue-600 text-white"
                  : "text-[var(--surface-text-muted)] hover:text-[var(--surface-text)]"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>
      <div ref={containerRef} className="w-full h-[260px] md:h-[340px]" />
      <SelectedEventPanel
        date={selectedDate}
        events={selectedEvents}
        onClose={() => setSelectedDate(null)}
      />
      <ChartEventStrip events={events} />
    </div>
  );
}

function SelectedEventPanel({
  date,
  events,
  onClose,
}: {
  date: string | null;
  events: StockEventMarker[];
  onClose: () => void;
}) {
  if (!date || events.length === 0) return null;
  return (
    <div className="mt-2 rounded-md border border-blue-500/30 bg-blue-500/5 px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-semibold text-[var(--surface-text)]">
          {formatEventDate(date)} 종합 원인
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded px-2 py-1 text-xs text-[var(--surface-text-muted)] hover:bg-[var(--surface-section-hover)]"
        >
          닫기
        </button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {events.flatMap((event) => event.keywords?.length ? event.keywords : [event.keyword]).map((keyword, index) => (
          <span
            key={`${keyword}-${index}`}
            className={`rounded border px-2 py-1 text-xs ${eventTone(events[Math.min(index, events.length - 1)].direction)}`}
          >
            {keyword}
          </span>
        ))}
      </div>
      <div className="mt-2 space-y-1">
        {events.slice(0, 3).map((event) => (
          <p key={event.id} className="text-xs leading-relaxed text-[var(--surface-text-muted)]">
            {event.summary}
          </p>
        ))}
      </div>
    </div>
  );
}

function ChartEventStrip({ events }: { events: StockEventMarker[] }) {
  const groups = groupEventsByDate(events).slice(0, 5);
  if (groups.length === 0) {
    return (
      <div className="mt-2 rounded-md border border-dashed border-[var(--surface-border)] px-3 py-2 text-xs text-[var(--surface-text-muted)]">
        아직 확정된 과거 원인 키워드가 없습니다. 과거 데이터 기준 키워드 추출이 끝나면 상승·하락 원인이 여기에 기록됩니다.
      </div>
    );
  }

  return (
    <div className="mt-2 flex gap-1.5 overflow-x-auto pb-1">
      {groups.map((group) => (
        <div
          key={group.date}
          className="min-w-[230px] rounded-md border border-[var(--surface-border)] bg-[var(--surface-card)] px-2.5 py-2"
        >
          <div className="flex items-center justify-between gap-2 text-[10px]">
            <span className="font-medium text-[var(--surface-text-muted)]">
              {formatEventDate(group.date)}
            </span>
            <span className="text-[var(--surface-text-subtle)]">
              원인 {group.events.length}개
            </span>
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1">
            {group.events.slice(0, 5).map((event) => (
              <a
                key={event.id}
                href={event.url || undefined}
                target={event.url ? "_blank" : undefined}
                rel={event.url ? "noreferrer" : undefined}
                className={`max-w-full rounded border px-1.5 py-0.5 text-[10px] transition-colors ${eventTone(event.direction)}`}
                title={`${SOURCE_LABEL[event.source_type]} · ${event.summary}`}
              >
                <span className="mr-1 opacity-70">{SOURCE_LABEL[event.source_type]}</span>
                <span>{event.keyword}</span>
              </a>
            ))}
            {group.events.length > 5 ? (
              <span className="rounded border border-[var(--surface-border)] px-1.5 py-0.5 text-[10px] text-[var(--surface-text-muted)]">
                +{group.events.length - 5}
              </span>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}

const SOURCE_LABEL: Record<EventSourceType, string> = {
  daily_driver: "종합",
  price_move: "가격원인",
  news: "뉴스",
  catalyst: "예정",
};

function markerPosition(direction: EventDirection): "aboveBar" | "belowBar" | "inBar" {
  if (direction === "positive") return "belowBar";
  if (direction === "negative") return "aboveBar";
  return "inBar";
}

function markerShape(direction: EventDirection): "arrowUp" | "arrowDown" | "circle" | "square" {
  if (direction === "positive") return "arrowUp";
  if (direction === "negative") return "arrowDown";
  if (direction === "mixed") return "square";
  return "circle";
}

function markerColor(direction: EventDirection, mode: "light" | "dark"): string {
  if (direction === "positive") return mode === "dark" ? "#f87171" : "#dc2626";
  if (direction === "negative") return mode === "dark" ? "#60a5fa" : "#2563eb";
  if (direction === "mixed") return mode === "dark" ? "#fbbf24" : "#a16207";
  return mode === "dark" ? "#94a3b8" : "#64748b";
}

function eventTone(direction: EventDirection): string {
  if (direction === "positive") {
    return "border-red-500/30 bg-red-500/10 text-red-700 hover:bg-red-500/15 dark:text-red-300";
  }
  if (direction === "negative") {
    return "border-blue-500/30 bg-blue-500/10 text-blue-700 hover:bg-blue-500/15 dark:text-blue-300";
  }
  if (direction === "mixed") {
    return "border-amber-500/30 bg-amber-500/10 text-amber-700 hover:bg-amber-500/15 dark:text-amber-300";
  }
  return "border-[var(--surface-border)] bg-[var(--surface-card)] text-[var(--surface-text-muted)] hover:bg-[var(--surface-section-hover)]";
}

function formatEventDate(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function timeToDateString(t: Time): string {
  if (typeof t === "string") return t.slice(0, 10);
  if (typeof t === "number") return new Date(t * 1000).toISOString().slice(0, 10);
  const bd = t as { year: number; month: number; day: number };
  return `${bd.year}-${String(bd.month).padStart(2, "0")}-${String(bd.day).padStart(2, "0")}`;
}

function selectChartEvents(events: StockEventMarker[]): StockEventMarker[] {
  const byDate = new Map<string, StockEventMarker>();
  for (const event of events) {
    const existing = byDate.get(event.date);
    if (!existing || eventPriority(event) > eventPriority(existing)) {
      byDate.set(event.date, event);
    }
  }
  return Array.from(byDate.values())
    .sort((a, b) => b.date.localeCompare(a.date))
    .slice(0, 10);
}

function groupEventsByDate(events: StockEventMarker[]): Array<{
  date: string;
  events: StockEventMarker[];
}> {
  const seen = new Set<string>();
  const byDate = new Map<string, StockEventMarker[]>();
  for (const event of events) {
    const key = `${event.date}|${event.source_type}|${event.keyword}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const list = byDate.get(event.date) ?? [];
    list.push(event);
    byDate.set(event.date, list);
  }
  return Array.from(byDate.entries())
    .map(([date, list]) => ({
      date,
      events: list.sort((a, b) => eventPriority(b) - eventPriority(a)),
    }))
    .sort((a, b) => b.date.localeCompare(a.date));
}

function eventPriority(event: StockEventMarker): number {
  const sourceScore: Record<EventSourceType, number> = {
    daily_driver: 5,
    price_move: 4,
    catalyst: 3,
    news: 2,
  };
  const directionScore: Record<EventDirection, number> = {
    positive: 2,
    negative: 2,
    mixed: 1,
    neutral: 0,
  };
  return sourceScore[event.source_type] * 10 + directionScore[event.direction];
}

function formatKoreanDate(t: Time, includeYear: boolean): string {
  const d = toDate(t);
  const y = d.getFullYear() % 100;
  const m = d.getMonth() + 1;
  const day = d.getDate();
  return includeYear ? `${y}년 ${m}월 ${day}일` : `${m}월 ${day}일`;
}

function formatTickKorean(t: Time): string {
  const d = toDate(t);
  const day = d.getDate();
  const month = d.getMonth() + 1;
  // 월 첫째 주(1~3일)면 "M월" 라벨, 그 외 "D일"만 — 컴팩트.
  return day <= 3 ? `${month}월` : `${day}일`;
}

function toDate(t: Time): Date {
  if (typeof t === "string") return new Date(t);
  if (typeof t === "number") return new Date(t * 1000);
  // BusinessDay
  const bd = t as { year: number; month: number; day: number };
  return new Date(bd.year, bd.month - 1, bd.day);
}
