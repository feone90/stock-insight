"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { getOntologyGraph } from "@/services/api";
import { useTheme } from "@/lib/use-theme";
import type { GraphLink, GraphNode, GraphPayload } from "@/types/ontology";

/**
 * Stock Universe ontology graph (P3).
 *
 * - Force-directed layout via react-force-graph-2d (canvas, SSR off).
 * - Center node = the ticker the user is on. 1-hop default; 2-hop optional.
 * - Edge color by source (sec_8k 파란, news 빨간, sector_match 회색, ...).
 * - Edge thickness = strength × confidence. inverse signal은 점선으로.
 * - 클릭 시 해당 종목 카드로 이동.
 */

const ForceGraph2D = dynamic(
  () => import("react-force-graph-2d").then((mod) => mod.default),
  { ssr: false },
);

// Edge 색 — relation_type 별 의미 차별화. peer(섹터)는 옅은 회색,
// competitor·inverse는 빨강, contract는 진한 파랑, complementary는 보라.
const RELATION_COLOR: Record<string, string> = {
  peer: "rgba(148, 163, 184, 0.35)", // slate 400 / 35% — 약하게
  competitor: "#dc2626",              // red 600
  contract_supplier: "#2563eb",       // blue 600
  contract_customer: "#0891b2",       // cyan 600
  complementary: "#a855f7",           // purple 500
  supply_upstream: "#0369a1",         // sky 700
  supply_downstream: "#0e7490",       // teal 700
  group: "#7c3aed",                   // violet 600
  theme: "#db2777",                   // pink 600
  macro: "#475569",                   // slate 600
  regulatory_link: "#ea580c",         // orange 600
};

const SOURCE_COLOR: Record<string, string> = {
  sec_8k: "#2563eb",
  dart_contract: "#f59e0b",
  news: "#dc2626",
  sector_match: "rgba(148, 163, 184, 0.35)",
  curated_relation: "#a855f7",
};

const TIER_COLOR_LIGHT: Record<number, string> = {
  1: "#1f2937", // slate 800
  2: "#0ea5e9", // sky 500 — user-touched
  3: "#cbd5e1", // slate 300
};
const TIER_COLOR_DARK: Record<number, string> = {
  1: "#cbd5e1",
  2: "#38bdfa",
  3: "#475569",
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ForceGraphRef = any;

export function OntologyGraph({ ticker }: { ticker: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const fgRef = useRef<ForceGraphRef>(null);
  const [data, setData] = useState<GraphPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [depth, setDepth] = useState(1);
  const { mode } = useTheme();

  // 노드 간 거리 / charge 강하게 — 라벨 안 겹치게.
  useEffect(() => {
    if (!fgRef.current || !data) return;
    try {
      fgRef.current.d3Force?.("charge")?.strength?.(-400);
      fgRef.current.d3Force?.("link")?.distance?.(110);
      fgRef.current.d3Force?.("center")?.strength?.(0.05);
    } catch {
      /* noop — older versions may not expose forces */
    }
  }, [data]);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setData(null);
    getOntologyGraph(ticker, { depth, cap: 200 })
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, depth]);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const update = () => {
      const w = node.clientWidth;
      const h = Math.max(500, window.innerHeight - 240);
      setSize((prev) => (prev.width === w && prev.height === h ? prev : { width: w, height: h }));
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(node);
    window.addEventListener("resize", update);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", update);
    };
  }, []);

  // Data shape that react-force-graph mutates in place — useMemo so the
  // simulation isn't reset on every parent re-render.
  const graphData = useMemo(
    () =>
      data
        ? {
            nodes: data.nodes.map((n) => ({ ...n })),
            links: data.links.map((l) => ({ ...l })),
          }
        : null,
    [data],
  );

  if (error) {
    return (
      <div className="rounded-md border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-700 dark:text-red-300">
        그래프 데이터 가져오기 실패: {error}
      </div>
    );
  }
  if (!data || !graphData) {
    return (
      <div className="rounded-md border border-[var(--surface-border)] bg-[var(--surface-card)] p-12 text-center text-sm text-[var(--surface-text-muted)]">
        관계 그래프 불러오는 중...
      </div>
    );
  }

  const tierColors = mode === "dark" ? TIER_COLOR_DARK : TIER_COLOR_LIGHT;
  const renderWidth = size.width || 1200;
  const renderHeight = size.height || 600;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="font-medium">{data.center}</span>
        <span className="text-[var(--surface-text-muted)]">
          노드 {data.nodes.length} · 연결 {data.links.length}
        </span>
        <div className="flex gap-1">
          {[1, 2].map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDepth(d)}
              className={`px-2.5 py-1 rounded text-xs border transition-colors ${
                d === depth
                  ? "bg-blue-600 text-white border-blue-600"
                  : "border-[var(--surface-border)] hover:bg-[var(--surface-section-hover)]"
              }`}
            >
              {d}-hop
            </button>
          ))}
        </div>
        <Legend />
      </div>
      <div
        ref={containerRef}
        className="rounded-lg border border-[var(--surface-border)] bg-[var(--surface-card)] overflow-hidden"
        style={{ height: renderHeight }}
      >
        <ForceGraph2D
            ref={fgRef}
            graphData={graphData}
            width={renderWidth}
            height={renderHeight}
            onEngineStop={() => {
              try {
                fgRef.current?.zoomToFit?.(400, 60);
              } catch {
                /* noop */
              }
            }}
            backgroundColor="rgba(0,0,0,0)"
            nodeRelSize={5}
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.3}
            cooldownTime={6000}
            nodeColor={(n) =>
              (n as GraphNode).is_center
                ? "#f59e0b"
                : tierColors[(n as GraphNode).tier] ?? tierColors[1]
            }
            nodeVal={(n) => ((n as GraphNode).is_center ? 6 : 1.5)}
            nodeLabel={(n) => {
              const node = n as GraphNode;
              const change = node.today_change_pct;
              const changeStr =
                change == null
                  ? ""
                  : ` · ${change > 0 ? "+" : ""}${change.toFixed(1)}%`;
              return `${node.name} (${node.ticker})${changeStr} · ${node.sector ?? ""}`;
            }}
            nodeCanvasObjectMode={() => "after"}
            nodeCanvasObject={(n, ctx, scale) => {
              const node = n as GraphNode & { x?: number; y?: number };
              if (node.x == null || node.y == null) return;
              // Constant on-screen font size (clamped) — 적당히 크고 읽기 쉽게.
              const baseFont = node.is_center ? 14 : 11;
              const fontSize = baseFont / Math.min(Math.max(scale, 0.6), 2.5);
              ctx.font = `${node.is_center ? "bold " : ""}${fontSize}px sans-serif`;
              ctx.fillStyle =
                mode === "dark" ? "rgba(241,245,249,0.95)" : "rgba(15,23,42,0.95)";
              ctx.textAlign = "center";
              ctx.textBaseline = "top";
              const radius = node.is_center ? 11 : 5;
              const label = node.is_center
                ? node.name
                : `${node.name} (${node.ticker})`;
              ctx.fillText(label, node.x, node.y + radius + 3);
            }}
            linkColor={(l) => {
              const link = l as GraphLink;
              return (
                RELATION_COLOR[link.relation_type] ?? RELATION_COLOR.peer
              );
            }}
            linkWidth={(l) => {
              const link = l as GraphLink;
              // peer (sector) 는 가는 옅은 선, 그 외 의미 있는 관계는 굵게.
              const base = link.relation_type === "peer" ? 0.6 : 1.5;
              return base + link.strength * link.confidence * 3.5;
            }}
            linkLineDash={(l) =>
              (l as GraphLink).signal_direction === "inverse" ? [5, 4] : null
            }
            linkLabel={(l) => {
              const link = l as GraphLink;
              return `${link.relation_type} · ${link.signal_direction} · 신뢰 ${(link.confidence * 100).toFixed(0)}%`;
            }}
            linkDirectionalArrowLength={3.5}
            linkDirectionalArrowRelPos={0.96}
            linkDirectionalArrowColor={(l) => {
              const link = l as GraphLink;
              return (
                RELATION_COLOR[link.relation_type] ?? RELATION_COLOR.peer
              );
            }}
            cooldownTicks={150}
            onNodeClick={(n) => {
              const node = n as GraphNode;
              window.location.href = `/v2/stock/${node.ticker}`;
            }}
          />
      </div>
    </div>
  );
}

function Legend() {
  return (
    <div className="ml-auto flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--surface-text-muted)]">
      <span className="flex items-center gap-1">
        <Dot color="#f59e0b" /> 중심
      </span>
      <span className="flex items-center gap-1">
        <Dot color="#0ea5e9" /> tier 2 (관심)
      </span>
      <span className="flex items-center gap-1">
        <Dot color="#94a3b8" /> tier 1
      </span>
      <span className="text-[var(--surface-text-subtle)]">|</span>
      <span className="flex items-center gap-1">
        <LineSwatch color="#dc2626" thick /> 경쟁
      </span>
      <span className="flex items-center gap-1">
        <LineSwatch color="#2563eb" thick /> 공급계약
      </span>
      <span className="flex items-center gap-1">
        <LineSwatch color="#a855f7" thick /> 상호보완
      </span>
      <span className="flex items-center gap-1">
        <LineSwatch color="rgba(148,163,184,0.7)" /> 동종업계
      </span>
      <span className="flex items-center gap-1">
        <span
          className="inline-block w-4 h-0 border-t border-dashed"
          style={{ borderColor: "#dc2626" }}
        />
        역신호
      </span>
    </div>
  );
}

function Dot({ color }: { color: string }) {
  return (
    <span
      className="inline-block w-2.5 h-2.5 rounded-full"
      style={{ backgroundColor: color }}
    />
  );
}
function LineSwatch({ color, thick }: { color: string; thick?: boolean }) {
  return (
    <span
      className={`inline-block w-4 ${thick ? "h-[2px]" : "h-px"}`}
      style={{ backgroundColor: color }}
    />
  );
}
