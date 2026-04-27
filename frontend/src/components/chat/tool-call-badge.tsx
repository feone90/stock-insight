"use client";

const TOOL_LABELS: Record<string, string> = {
  get_stock_snapshot: "스냅샷 조회",
  get_recent_news: "뉴스 검색",
  search_stocks: "종목 검색",
};

interface Props {
  tool: string;
  args: Record<string, unknown>;
  completed?: boolean;
}

export function ToolCallBadge({ tool, args, completed = false }: Props) {
  const label = TOOL_LABELS[tool] ?? tool;
  const ticker = typeof args.ticker === "string" ? args.ticker : undefined;
  const query = typeof args.query === "string" ? args.query : undefined;
  const arg = ticker ?? query ?? "";

  return (
    <div className="my-2 flex justify-center">
      <div
        className={`inline-flex items-center gap-1.5 rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-xs ${
          completed ? "text-slate-600" : "text-slate-400"
        }`}
        role="status"
        aria-live="polite"
      >
        <span>{arg ? `${arg} ${label}` : label}{!completed && " 중..."}</span>
      </div>
    </div>
  );
}
