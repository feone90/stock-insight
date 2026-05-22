"use client";

import Link from "next/link";
import { Bot, Clock3 } from "lucide-react";

export default function ChatPage() {
  return (
    <div className="mx-auto flex min-h-[calc(100vh-3.5rem)] max-w-2xl flex-col justify-center px-5 py-12">
      <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-6">
        <div className="inline-flex items-center gap-2 rounded border border-purple-500/25 bg-purple-500/10 px-2.5 py-1 text-xs font-medium text-purple-200">
          <Bot size={14} />
          Ask AI
        </div>
        <h1 className="mt-4 text-2xl font-semibold tracking-tight text-slate-50">
          대화형 분석은 준비중입니다
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-slate-400">
          지금 테스트 링크에서는 종목 카드와 포트폴리오 화면만 열어두었습니다.
          Ask AI는 답변 품질과 근거 표시를 더 다듬은 뒤 공개할 예정입니다.
        </p>
        <div className="mt-5 flex flex-col gap-2 sm:flex-row">
          <Link
            href="/portfolio"
            className="inline-flex items-center justify-center rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500"
          >
            포트폴리오 보기
          </Link>
          <Link
            href="/"
            className="inline-flex items-center justify-center rounded-md border border-slate-700 px-3 py-2 text-sm font-medium text-slate-300 transition-colors hover:border-slate-500 hover:text-slate-100"
          >
            즐겨찾기 목록
          </Link>
        </div>
        <div className="mt-5 flex items-center gap-2 border-t border-slate-800 pt-4 text-xs text-slate-500">
          <Clock3 size={13} />
          준비중 기능입니다.
        </div>
      </div>
    </div>
  );
}
