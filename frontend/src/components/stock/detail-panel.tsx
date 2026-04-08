import type { KeywordDetail } from "@/types/stock";

const TYPE_LABELS = {
  bullish: { label: "상승 요인", color: "text-green-400" },
  bearish: { label: "하락 요인", color: "text-red-400" },
  neutral: { label: "보합 요인", color: "text-slate-400" },
};

const IMPACT_LABELS = { high: "높음", mid: "중간", low: "낮음" };
const DURATION_LABELS = { short: "단기", mid: "중기", long: "장기" };

interface Props {
  keyword: KeywordDetail | null;
}

export function DetailPanel({ keyword }: Props) {
  if (!keyword) {
    return (
      <div>
        <h2 className="mb-3 text-sm font-bold text-slate-50">📋 상세 리포트</h2>
        <p className="text-sm text-slate-600">
          ← 키워드를 클릭하면 여기에 상세 내용이 표시됩니다
        </p>
      </div>
    );
  }

  const typeInfo = TYPE_LABELS[keyword.type];

  return (
    <div>
      <h2 className="mb-3 text-sm font-bold text-slate-50">📋 상세 리포트</h2>
      <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
        <div className={`mb-1 text-xs font-medium ${typeInfo.color}`}>
          {typeInfo.label}
        </div>
        <h3 className="mb-3 text-base font-bold text-slate-50">
          {keyword.keyword}
        </h3>
        <p className="mb-4 text-sm leading-relaxed text-slate-300">
          {keyword.detail}
        </p>
        <div className="space-y-2 text-xs text-slate-500">
          <div>📰 출처: {keyword.source}</div>
          <div className="flex gap-4">
            <span>
              📊 영향도:{" "}
              <span className="text-slate-300">
                {IMPACT_LABELS[keyword.impact_level as keyof typeof IMPACT_LABELS]}
              </span>
            </span>
            <span>
              ⏱ 지속성:{" "}
              <span className="text-slate-300">
                {DURATION_LABELS[keyword.duration as keyof typeof DURATION_LABELS]}
              </span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
