interface Props {
  summary: string;
  feedback: string;
}

export function AiFeedback({ summary, feedback }: Props) {
  return (
    <div className="rounded-lg border border-purple-500/30 bg-purple-500/5 p-4">
      <div className="mb-2 text-sm font-semibold text-purple-400">
        🤖 AI 피드백 &amp; 대책
      </div>
      <p className="mb-3 text-sm leading-relaxed text-slate-300">{summary}</p>
      <div className="rounded-md bg-slate-900/50 p-3">
        <div className="mb-1 text-xs font-medium text-purple-300">
          투자 전략 제안
        </div>
        <p className="text-sm leading-relaxed text-slate-300">{feedback}</p>
      </div>
    </div>
  );
}
