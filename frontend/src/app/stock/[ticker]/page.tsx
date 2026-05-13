"use client";

import { useParams } from "next/navigation";
import { StockCardPage } from "@/components/stock-v2/card-shell";

/**
 * Stock card page — canonical route.
 *
 * Routing migration finalized: 이전 v1 dashboard (price chart + AI feedback
 * + keyword section) 는 retire 됐고, /stock/[ticker] 는 ontology-aware analyst
 * 카드 (8 섹션) 를 직접 렌더한다. 옛 /v2/stock/[ticker] 경로는 제거됐다 —
 * 가족 demo 라 외부 북마크 우려 없음.
 */
export default function StockPage() {
  const params = useParams();
  const ticker = params.ticker as string;
  return <StockCardPage ticker={ticker} />;
}
