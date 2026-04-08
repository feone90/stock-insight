"use client";

import type { KeywordDetail } from "@/types/stock";
import { KeywordTag } from "./keyword-tag";

interface Props {
  keywords: KeywordDetail[];
  selectedKeyword: string | null;
  onSelect: (keyword: KeywordDetail) => void;
}

export function KeywordSection({ keywords, selectedKeyword, onSelect }: Props) {
  const bullish = keywords.filter((k) => k.type === "bullish");
  const bearish = keywords.filter((k) => k.type === "bearish");
  const neutral = keywords.filter((k) => k.type === "neutral");

  return (
    <div className="space-y-3">
      {bullish.length > 0 && (
        <div className="rounded-lg border border-green-500/30 bg-green-500/5 p-3">
          <div className="mb-2 text-sm font-semibold text-green-400">
            📈 상승 요인
          </div>
          <div className="flex flex-wrap gap-2">
            {bullish.map((k) => (
              <KeywordTag
                key={k.keyword}
                keyword={k}
                isSelected={selectedKeyword === k.keyword}
                onClick={() => onSelect(k)}
              />
            ))}
          </div>
        </div>
      )}
      {bearish.length > 0 && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3">
          <div className="mb-2 text-sm font-semibold text-red-400">
            📉 하락 요인
          </div>
          <div className="flex flex-wrap gap-2">
            {bearish.map((k) => (
              <KeywordTag
                key={k.keyword}
                keyword={k}
                isSelected={selectedKeyword === k.keyword}
                onClick={() => onSelect(k)}
              />
            ))}
          </div>
        </div>
      )}
      {neutral.length > 0 && (
        <div className="rounded-lg border border-slate-500/30 bg-slate-500/5 p-3">
          <div className="mb-2 text-sm font-semibold text-slate-400">
            ➡️ 보합 요인
          </div>
          <div className="flex flex-wrap gap-2">
            {neutral.map((k) => (
              <KeywordTag
                key={k.keyword}
                keyword={k}
                isSelected={selectedKeyword === k.keyword}
                onClick={() => onSelect(k)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
