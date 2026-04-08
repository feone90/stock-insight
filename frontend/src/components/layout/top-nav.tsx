import Link from "next/link";
import { StockSearch } from "@/components/search/stock-search";

export function TopNav() {
  return (
    <nav className="flex items-center justify-between border-b border-slate-800 bg-slate-950 px-6 py-3">
      <div className="flex items-center gap-4">
        <Link href="/" className="text-lg font-bold text-slate-50">
          📊 StockInsight
        </Link>
        <StockSearch />
      </div>
      <div className="flex items-center gap-4">
        <Link
          href="/"
          className="text-sm text-yellow-400 hover:text-yellow-300 transition-colors"
        >
          ⭐ 즐겨찾기
        </Link>
      </div>
    </nav>
  );
}
