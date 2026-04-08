"use client";

import type { KeywordDetail } from "@/types/stock";

const TYPE_STYLES = {
  bullish: {
    bg: "bg-green-500/10",
    border: "border-green-500/30",
    text: "text-green-400",
  },
  bearish: {
    bg: "bg-red-500/10",
    border: "border-red-500/30",
    text: "text-red-400",
  },
  neutral: {
    bg: "bg-slate-500/10",
    border: "border-slate-500/30",
    text: "text-slate-400",
  },
};

interface Props {
  keyword: KeywordDetail;
  isSelected: boolean;
  onClick: () => void;
}

export function KeywordTag({ keyword, isSelected, onClick }: Props) {
  const style = TYPE_STYLES[keyword.type];
  return (
    <button
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs font-medium transition-all ${style.bg} ${style.border} ${style.text} ${
        isSelected ? "ring-2 ring-blue-500 ring-offset-1 ring-offset-slate-950" : "hover:brightness-125"
      }`}
    >
      {keyword.keyword}
    </button>
  );
}
