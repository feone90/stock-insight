"use client";

import type { DailyKeyword } from "@/types/stock";

const TYPE_COLORS = {
  bullish: { bg: "bg-green-500/20", text: "text-green-400" },
  bearish: { bg: "bg-red-500/20", text: "text-red-400" },
  neutral: { bg: "bg-slate-500/20", text: "text-slate-400" },
};

interface Props {
  dailyKeywords: DailyKeyword[];
  selectedDate: string | null;
  onDateSelect: (date: string) => void;
}

export function KeywordTimeline({
  dailyKeywords,
  selectedDate,
  onDateSelect,
}: Props) {
  return (
    <div className="mt-2 border-t border-slate-800 pt-2">
      <div className="flex gap-1 overflow-x-auto">
        {dailyKeywords.map((dk) => {
          const colors = TYPE_COLORS[dk.type];
          const isSelected = selectedDate === dk.date;
          return (
            <button
              key={dk.date}
              onClick={() => onDateSelect(dk.date)}
              className={`flex flex-col items-center gap-1 rounded-md p-1.5 min-w-[80px] transition-colors ${
                isSelected ? "bg-slate-800" : "hover:bg-slate-900"
              }`}
            >
              <span className="text-[10px] text-slate-500">
                {dk.date.slice(5)}
              </span>
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] ${colors.bg} ${colors.text}`}
              >
                {dk.keyword}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
