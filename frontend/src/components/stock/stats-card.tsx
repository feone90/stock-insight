import type { StatsInfo } from "@/types/stock";

interface Props {
  stats: StatsInfo;
  market: string;
}

export function StatsCard({ stats, market }: Props) {
  const currency = market === "KRX" ? "원" : "$";
  const items = [
    { label: "시가총액", value: stats.market_cap },
    { label: "PER", value: `${stats.per}배` },
    { label: "PBR", value: `${stats.pbr}배` },
    { label: "배당수익률", value: `${stats.dividend_yield}%` },
    {
      label: "52주 최고",
      value: `${stats.high_52w.toLocaleString()}${currency}`,
      color: "text-green-400",
    },
    {
      label: "52주 최저",
      value: `${stats.low_52w.toLocaleString()}${currency}`,
      color: "text-red-400",
    },
  ];

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
      <h3 className="mb-3 text-sm font-bold text-slate-50">주요 지표</h3>
      <div className="grid grid-cols-2 gap-2 text-sm">
        {items.map((item) => (
          <div key={item.label} className="flex justify-between">
            <span className="text-slate-500">{item.label}</span>
            <span className={item.color ?? "text-slate-50"}>{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
