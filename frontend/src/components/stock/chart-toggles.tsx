"use client";

interface ToggleItem {
  key: string;
  label: string;
  color: string;
}

const TOGGLES: ToggleItem[] = [
  { key: "closeLine", label: "종가 라인", color: "#60a5fa" },
  { key: "ma5", label: "MA5", color: "#fbbf24" },
  { key: "ma20", label: "MA20", color: "#a78bfa" },
  { key: "ma60", label: "MA60", color: "#f472b6" },
];

interface Props {
  active: Record<string, boolean>;
  onToggle: (key: string) => void;
}

export function ChartToggles({ active, onToggle }: Props) {
  return (
    <div className="flex gap-3">
      {TOGGLES.map((t) => (
        <button
          key={t.key}
          onClick={() => onToggle(t.key)}
          className="flex items-center gap-1.5"
        >
          <div
            className={`h-4 w-8 rounded-full transition-colors ${
              active[t.key] ? "" : "bg-slate-700"
            }`}
            style={active[t.key] ? { backgroundColor: t.color } : {}}
          >
            <div
              className={`h-3.5 w-3.5 rounded-full bg-white transition-transform ${
                active[t.key] ? "translate-x-4" : "translate-x-0.5"
              }`}
              style={{ marginTop: "1px" }}
            />
          </div>
          <span
            className="text-xs"
            style={{ color: active[t.key] ? t.color : "#64748b" }}
          >
            {t.label}
          </span>
        </button>
      ))}
    </div>
  );
}
