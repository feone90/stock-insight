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

const RELATION_LABEL_KO: Record<string, string> = {
  peer: "동종업계",
  competitor: "경쟁",
  contract_supplier: "공급계약",
  contract_customer: "구매계약",
  complementary: "상호보완",
  supply_upstream: "공급-상류",
  supply_downstream: "공급-하류",
  group: "그룹사",
  theme: "테마",
  macro: "매크로",
  regulatory_link: "규제연동",
};

const SIGNAL_LABEL_KO: Record<string, string> = {
  positive: "↑ 동조",
  negative: "↓ 부정",
  inverse: "⇄ 역신호",
};

const SOURCE_LABEL_KO: Record<string, string> = {
  sector_match: "섹터매칭",
  sec_8k: "SEC 8-K",
  dart_contract: "DART 공시",
  news: "뉴스",
  curated_relation: "AI 큐레이션",
  candidate_promote: "후보 승격",
  llm_web_search: "웹 탐색",
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

// 2026-05-14: 카드 3-tier(core/business/context)와 그래프 시각 hierarchy 일치
// 시키려는 분류. classifyEdgeTier 는 edge 의 source/relation_type/confidence
// 셋으로 강도 판정. core = filing 또는 high-conf news, business = news rationale,
// context = sector_match peer. project_ontology_codex_review §사용자 정정.
type EdgeTier = "core" | "business" | "context";

function classifyEdgeTier(link: GraphLink): EdgeTier {
  // context: mechanical sector match 또는 peer/group/theme/macro
  if (
    link.src_label === "sector_match" ||
    link.relation_type === "peer" ||
    link.relation_type === "group" ||
    link.relation_type === "theme" ||
    link.relation_type === "macro"
  ) {
    return "context";
  }
  // core: filing 증거 or confidence >= 0.8
  if (
    link.src_label === "sec_8k" ||
    link.src_label === "sec_10k_risk" ||
    link.src_label === "dart_contract" ||
    (link.confidence ?? 0) >= 0.8
  ) {
    return "core";
  }
  return "business";
}

export function OntologyGraph({ ticker }: { ticker: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const fgRef = useRef<ForceGraphRef>(null);
  const [data, setData] = useState<GraphPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [depth, setDepth] = useState(1);
  const [selectedLink, setSelectedLink] = useState<GraphLink | null>(null);
  // 카드 3-tier UI 와 일관 — sector peer 숨기면 진짜 신호만 한눈에.
  const [showContext, setShowContext] = useState(true);
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
  // simulation isn't reset on every parent re-render. Context filter 도
  // 이 시점에 적용 — toggle 시 새 simulation 으로 re-layout.
  const graphData = useMemo(() => {
    if (!data) return null;
    const links = data.links
      .map((l) => ({ ...l }))
      .filter((l) => showContext || classifyEdgeTier(l) !== "context");
    // context hide 시 고립 노드도 제거. center 는 항상 keep.
    const linkedTickers = new Set<string>();
    for (const l of links) {
      const s = typeof l.source === "string" ? l.source : (l.source as unknown as { ticker?: string })?.ticker;
      const t = typeof l.target === "string" ? l.target : (l.target as unknown as { ticker?: string })?.ticker;
      if (s) linkedTickers.add(s);
      if (t) linkedTickers.add(t);
    }
    const nodes = data.nodes
      .map((n) => ({ ...n }))
      .filter((n) => showContext || n.is_center || linkedTickers.has(n.ticker));
    return { nodes, links };
  }, [data, showContext]);

  const tierCounts = useMemo(() => {
    if (!data) return { core: 0, business: 0, context: 0 };
    let core = 0, business = 0, context = 0;
    for (const l of data.links) {
      const t = classifyEdgeTier(l);
      if (t === "core") core++;
      else if (t === "business") business++;
      else context++;
    }
    return { core, business, context };
  }, [data]);

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
          <span className="text-amber-700 dark:text-amber-300 font-medium">
            핵심 {tierCounts.core}
          </span>
          {" · "}
          <span>사업 {tierCounts.business}</span>
          {" · "}
          <span className="text-[var(--surface-text-subtle)]">
            컨텍스트 {tierCounts.context}
          </span>
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
        <button
          type="button"
          onClick={() => setShowContext((v) => !v)}
          className={`px-2.5 py-1 rounded text-xs border transition-colors ${
            showContext
              ? "border-[var(--surface-border)] text-[var(--surface-text-muted)] hover:bg-[var(--surface-section-hover)]"
              : "bg-amber-500 text-white border-amber-500"
          }`}
          title="동종업계 / 그룹 / 테마 같은 컨텍스트 관계 숨기기 → 핵심 신호만 한눈에"
        >
          {showContext ? "🎯 핵심만 보기" : "🔗 컨텍스트도 보기"}
        </button>
        <Legend />
      </div>
      <div
        ref={containerRef}
        className="relative rounded-lg border border-[var(--surface-border)] bg-[var(--surface-card)] overflow-hidden"
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
              const tier = classifyEdgeTier(link);
              // Tier 기반 색/투명도 — 카드 3-tier 와 일관. core 는 진하고,
              // context 는 매우 옅어 진짜 신호가 시각적으로 떠오름.
              if (tier === "context") {
                return mode === "dark"
                  ? "rgba(148, 163, 184, 0.18)"  // slate 400 18%
                  : "rgba(148, 163, 184, 0.22)";
              }
              if (tier === "core") {
                // core 는 amber 강조 + relation_type 색 mix. 가장 두드러지게.
                return RELATION_COLOR[link.relation_type] ?? "#f59e0b";
              }
              // business — 원 relation_type 색
              return RELATION_COLOR[link.relation_type] ?? RELATION_COLOR.peer;
            }}
            linkWidth={(l) => {
              const link = l as GraphLink;
              const tier = classifyEdgeTier(link);
              // Tier 별 굵기 차이를 크게. context 는 매우 가늘게, core 는 굵게.
              if (tier === "context") return 0.4;
              const base = tier === "core" ? 2.5 : 1.5;
              return base + link.strength * link.confidence * 3.5;
            }}
            linkLineDash={(l) =>
              (l as GraphLink).signal_direction === "inverse" ? [5, 4] : null
            }
            linkLabel={(l) => {
              const link = l as GraphLink;
              const rel = RELATION_LABEL_KO[link.relation_type] ?? link.relation_type;
              const sig = SIGNAL_LABEL_KO[link.signal_direction] ?? link.signal_direction;
              const conf = `신뢰 ${(link.confidence * 100).toFixed(0)}%`;
              const head = `${rel} · ${sig} · ${conf}`;
              if (link.rationale && link.rationale.trim()) {
                const short =
                  link.rationale.length > 80
                    ? link.rationale.slice(0, 80) + "…"
                    : link.rationale;
                return `${head}\n근거: ${short}\n(선 클릭 → 전체 근거)`;
              }
              return `${head} · (출처: ${SOURCE_LABEL_KO[link.src_label] ?? link.src_label})`;
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
              window.location.href = `/stock/${node.ticker}`;
            }}
            onLinkClick={(l) => {
              setSelectedLink(l as GraphLink);
            }}
            onBackgroundClick={() => setSelectedLink(null)}
          />
        {selectedLink ? (
          <LinkDetailPanel
            link={selectedLink}
            onClose={() => setSelectedLink(null)}
          />
        ) : null}
      </div>
    </div>
  );
}

function LinkDetailPanel({
  link,
  onClose,
}: {
  link: GraphLink;
  onClose: () => void;
}) {
  const rel = RELATION_LABEL_KO[link.relation_type] ?? link.relation_type;
  const sig = SIGNAL_LABEL_KO[link.signal_direction] ?? link.signal_direction;
  const src = SOURCE_LABEL_KO[link.src_label] ?? link.src_label;
  const srcId =
    typeof link.source === "string"
      ? link.source
      : ((link.source as unknown as { ticker?: string })?.ticker ?? "?");
  const tgtId =
    typeof link.target === "string"
      ? link.target
      : ((link.target as unknown as { ticker?: string })?.ticker ?? "?");
  const color = RELATION_COLOR[link.relation_type] ?? RELATION_COLOR.peer;
  return (
    <div
      className="absolute right-3 top-3 w-[320px] max-w-[calc(100%-1.5rem)] rounded-md border border-[var(--surface-border)] bg-[var(--surface-card)]/95 backdrop-blur p-3 text-sm shadow-lg"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-[13px] font-semibold">
            <span className="font-mono">{srcId}</span>
            <span
              className="inline-block h-[2px] w-5 align-middle"
              style={{ backgroundColor: color }}
            />
            <span className="font-mono">{tgtId}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
            <span
              className="rounded-sm px-1.5 py-0.5 font-medium text-white"
              style={{ backgroundColor: color }}
            >
              {rel}
            </span>
            <span className="text-[var(--surface-text-muted)]">{sig}</span>
            <span className="text-[var(--surface-text-muted)]">
              · 신뢰 {(link.confidence * 100).toFixed(0)}%
            </span>
            <span className="text-[var(--surface-text-muted)]">
              · 강도 {(link.strength * 100).toFixed(0)}%
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="닫기"
          className="shrink-0 text-[var(--surface-text-muted)] hover:text-[var(--surface-text)] text-lg leading-none"
        >
          ×
        </button>
      </div>

      {link.rationale && link.rationale.trim() ? (
        <div className="mb-2 rounded-sm border border-[var(--surface-border)]/60 bg-[var(--surface-section)] p-2">
          <div className="mb-0.5 text-[10px] uppercase tracking-wide text-[var(--surface-text-muted)]">
            왜 이 관계?
          </div>
          <p className="text-[13px] leading-relaxed text-[var(--surface-text)]">
            {link.rationale}
          </p>
        </div>
      ) : (
        <p className="mb-2 text-xs italic text-[var(--surface-text-subtle)]">
          LLM 추출 근거 없음 — rule-based ({src}) 매핑.
        </p>
      )}

      <div className="flex items-center justify-between text-[11px] text-[var(--surface-text-muted)]">
        <span>출처: {src}</span>
        {link.src_url ? (
          <a
            href={link.src_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 dark:text-blue-400 hover:underline"
          >
            원문 ↗
          </a>
        ) : null}
      </div>
    </div>
  );
}

function Legend() {
  return (
    <div className="ml-auto flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--surface-text-muted)]">
      <span className="flex items-center gap-1">
        <LineSwatch color="#dc2626" thick /> 🔑 핵심 (filing·고신뢰)
      </span>
      <span className="flex items-center gap-1">
        <LineSwatch color="#a855f7" /> 📝 사업 (뉴스 인용)
      </span>
      <span className="flex items-center gap-1">
        <LineSwatch color="rgba(148,163,184,0.4)" /> 🔗 컨텍스트 (동종)
      </span>
      <span className="flex items-center gap-1">
        <span
          className="inline-block w-4 h-0 border-t border-dashed"
          style={{ borderColor: "#dc2626" }}
        />
        ⇄ 역신호
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
