"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { OntologyGraph } from "@/components/stock-v2/ontology-graph";

/**
 * Stock Universe ontology graph page — canonical route /stock/[ticker]/graph.
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
              href={`/stock/${ticker}`}
              className="text-sm text-[var(--surface-text-muted)] hover:text-[var(--surface-text)]"
            >
              ← {ticker.toUpperCase()} 카드로
            </Link>
            <h1 className="text-lg font-semibold tracking-tight">사업 관계망</h1>
            <span className="text-xs text-[var(--surface-text-muted)]">
              종목 간 직접·연쇄 관계
            </span>
          </div>
        </div>
        <p className="mb-3 text-sm text-[var(--surface-text-muted)]">
          중심 종목과 사업상 연결된 고객·공급망·경쟁·상호보완 관계를 보여줍니다.
          <span className="ml-1 text-[var(--surface-text-subtle)]">
            선을 클릭하면 왜 연결됐는지와 출처를 확인할 수 있습니다.
          </span>
        </p>
        <OntologyGraph ticker={ticker} />
      </div>
    </div>
  );
}
