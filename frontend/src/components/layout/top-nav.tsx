"use client";

import Link from "next/link";
import { useState } from "react";
import { StockSearch } from "@/components/search/stock-search";
import { syncAll } from "@/services/api";

export function TopNav() {
  const [syncing, setSyncing] = useState(false);

  const handleSyncAll = async () => {
    setSyncing(true);
    try {
      const result = await syncAll();
      const { stocks_synced, total_synced, errors } = result;
      const summary = Object.entries(total_synced)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => `${k} ${v}건`)
        .join(", ");
      alert(
        `전체 동기화 완료 (${stocks_synced.length}개 종목)\n${summary || "변경 없음"}${
          errors.length > 0 ? `\n⚠️ ${errors.join("\n")}` : ""
        }`
      );
    } catch {
      alert("전체 동기화 실패");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <nav className="flex items-center justify-between border-b border-slate-800 bg-slate-950 px-6 py-3">
      <div className="flex items-center gap-4">
        <Link href="/" className="text-lg font-bold text-slate-50">
          📊 StockInsight
        </Link>
        <StockSearch />
      </div>
      <div className="flex items-center gap-4">
        <button
          onClick={handleSyncAll}
          disabled={syncing}
          className="rounded-md border border-slate-700 bg-slate-800 px-3 py-1 text-sm text-slate-300 transition-colors hover:bg-slate-700 disabled:opacity-50"
        >
          {syncing ? "동기화 중..." : "전체 동기화"}
        </button>
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
