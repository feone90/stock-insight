"use client";

const PERIODS = [
  { key: "daily", label: "일간" },
  { key: "weekly", label: "주간" },
  { key: "monthly", label: "월간" },
  { key: "quarterly", label: "분기" },
  { key: "semi_annual", label: "반기" },
  { key: "annual", label: "연간" },
];

interface Props {
  selected: string;
  onSelect: (period: string) => void;
}

export function PeriodTabs({ selected, onSelect }: Props) {
  return (
    <div className="flex gap-1 rounded-lg bg-slate-950 p-1">
      {PERIODS.map((p) => (
        <button
          key={p.key}
          onClick={() => onSelect(p.key)}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            selected === p.key
              ? "bg-slate-800 text-slate-50"
              : "text-slate-500 hover:text-slate-300"
          }`}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}
