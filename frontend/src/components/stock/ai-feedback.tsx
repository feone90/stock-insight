"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  summary: string;
  feedback: string;
}

export function AiFeedback({ summary, feedback }: Props) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-purple-500/30 bg-purple-500/5 p-4">
        <div className="mb-3 text-sm font-semibold text-purple-400">
          AI 시장 분석
        </div>
        <div className="prose prose-invert prose-sm max-w-none text-slate-300 leading-relaxed [&_strong]:text-slate-100 [&_table]:text-xs [&_th]:text-slate-400 [&_td]:text-slate-300 [&_td]:py-1 [&_th]:py-1">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{summary}</ReactMarkdown>
        </div>
      </div>

      <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 p-4">
        <div className="mb-3 text-sm font-semibold text-blue-400">
          투자 전략
        </div>
        <div className="prose prose-invert prose-sm max-w-none text-slate-300 leading-relaxed [&_strong]:text-slate-100 [&_table]:text-xs [&_th]:text-slate-400 [&_td]:text-slate-300 [&_td]:py-1 [&_th]:py-1 [&_table]:w-full">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{feedback}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
