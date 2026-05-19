"use client";

import { StockCardPage } from "@/components/stock-v2/card-shell";

/**
 * Client wrapper — page.tsx 가 server component (generateMetadata 필요) 가
 * 됐으므로 useParams/useState 등 client hook 쓰는 본문을 여기로 분리.
 */
export function StockPageClient({ ticker }: { ticker: string }) {
  return <StockCardPage ticker={ticker} />;
}
