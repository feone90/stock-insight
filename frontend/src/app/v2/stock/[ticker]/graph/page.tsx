"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { OntologyGraph } from "@/components/stock-v2/ontology-graph";

/**
 * Stock Universe ontology graph page (P3).
 * Route: /v2/stock/[ticker]/graph
 */
export default function StockGraphPage() {
  const params = useParams();
  const ticker = params.ticker as string;
  return (
    <div className="min-h-screen bg-[var(--surface-bg)] text-[var(--surface-text)]">
      <div className="mx-auto max-w-[1400px] px-4 py-6 md:py-8">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-baseline gap-3">
            <Link
              href={`/v2/stock/${ticker}`}
              className="text-sm text-[var(--surface-text-muted)] hover:text-[var(--surface-text)]"
            >
              ← {ticker.toUpperCase()} 카드로
            </Link>
            <h1 className="text-lg font-semibold tracking-tight">Ontology</h1>
            <span className="text-xs text-[var(--surface-text-muted)]">
              종목 관계 그래프
            </span>
          </div>
        </div>
        <p className="mb-3 text-sm text-[var(--surface-text-muted)]">
          중심 종목과 직접 / 간접 관계가 있는 종목들. 노드 클릭 시 해당 종목 카드로 이동.
          <span className="ml-1 text-[var(--surface-text-subtle)]">
            · 선(엣지)을 클릭하면 “왜 이 관계인지” 근거가 우측에 표시됩니다.
          </span>
        </p>
        <OntologyGraph ticker={ticker} />
      </div>
    </div>
  );
}
