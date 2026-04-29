"use client";

import { useParams } from "next/navigation";
import { StockCardPage } from "@/components/stock-v2/card-shell";

/**
 * v2 stock card — temporary route while v1 (`/stock/[ticker]`) stays live.
 * Sub-phase F flips the canonical route.
 *
 * Plan §4 (routing).
 */
export default function StockCardV2Page() {
  const params = useParams();
  const ticker = params.ticker as string;
  return <StockCardPage ticker={ticker} />;
}
