"use client";

import type { Insider } from "@/types/card";
import { SectionShell } from "./section-shell";

/**
 * 임원 매매 신고 (US-only, SEC Form 4).
 *
 * Codex 시니어 트레이더 권고(2026-05-14): "insider buying/selling and
 * institutional position changes are table-stakes context, especially for
 * small/mid caps". 본 섹션은 filing 수 + 최근 신고 리스트(원문 링크)까지.
 * 매수/매도 분류(transaction code P/S/A)는 Form 4 XML 파싱 follow-up.
 *
 * UI 카피 가이드(memory: feedback_card_user_facing_copy):
 * - "Form 4" / "SEC" 약어 노출 X
 * - "임원이 자기 회사 주식을 매매한 미국 증권관리위원회 공식 신고" 식 풀어쓰기
 * - 빈 데이터면 card-shell 단에서 섹션 자체 숨김.
 */
export function InsiderSection({ insider }: { insider: Insider }) {
  const compact = `최근 ${insider.window_days}일 임원 매매 신고 ${insider.filing_count}건`;
  return (
    <SectionShell
      emoji="🏛️"
      title="임원 매매 신고"
      compact={<span>{compact}</span>}
      expanded={<InsiderExpanded insider={insider} />}
      helpText={
        <div className="space-y-1.5">
          <p>
            <strong>회사 임원·이사·5%+ 대주주가 자기 회사 주식을 매수·매도하면
            미국 증권관리위원회(SEC)에 의무 신고</strong>. 그 신고 건수를 보여줘요.
          </p>
          <ul className="ml-3 space-y-0.5 list-disc">
            <li><strong>임원 매수가 많음</strong> — 회사 내부 사람들이 미래에 자신감 있다는 신호</li>
            <li><strong>임원 매도가 많음</strong> — 위험 신호일 수도, 단순 세금/옵션 행사일 수도</li>
            <li>매수/매도 분류는 "원문 보기" 클릭으로 SEC 원본에서 확인</li>
          </ul>
          <p className="text-[var(--surface-text-muted)] mt-1">
            US 종목만. KR 대량보유공시(5%) 는 별도 출처 (추후).
          </p>
        </div>
      }
    />
  );
}

function InsiderExpanded({ insider }: { insider: Insider }) {
  const help = buildHelp(insider.filing_count, insider.window_days);
  return (
    <div className="space-y-2 text-xs">
      <p className="text-sm font-medium">
        최근 {insider.window_days}일 임원 매매 신고 {insider.filing_count}건
      </p>
      <p className="text-[11px] text-[var(--surface-text-subtle)]">→ {help}</p>
      <p className="text-[11px] text-[var(--surface-text-subtle)]">
        임원이 자기 회사 주식을 매수/매도한 미국 증권관리위원회 공식 신고
        입니다. 매수/매도 분류는 원문에서 확인할 수 있어요.
      </p>
      {insider.recent.length > 0 ? (
        <ul className="space-y-1 mt-1">
          {insider.recent.slice(0, 5).map((f) => (
            <li key={f.accession} className="flex items-baseline gap-2">
              <span className="text-[var(--surface-text-muted)] tabular-nums">
                {f.filing_date}
              </span>
              {f.url ? (
                <a
                  href={f.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-600 dark:text-blue-400 hover:underline truncate"
                >
                  원문 보기 ↗
                </a>
              ) : (
                <span className="text-[var(--surface-text-muted)]">
                  {f.accession}
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : null}
      {insider.as_of ? (
        <p className="text-[11px] italic text-[var(--surface-text-subtle)]">
          출처: 미국 증권관리위원회 EDGAR (Form 4, 최근 신고 {insider.as_of})
        </p>
      ) : null}
    </div>
  );
}

function buildHelp(count: number, windowDays: number): string {
  if (count === 0) {
    return "신고 없음 — 임원 매매 신호 정보 부족";
  }
  if (count <= 2) {
    return `${windowDays}일에 ${count}건은 일반 수준 (정기 매매·옵션 행사 가능성)`;
  }
  if (count <= 5) {
    return `${windowDays}일에 ${count}건은 평균보다 잦음 — 원문에서 매수/매도 확인 권장`;
  }
  return `${windowDays}일에 ${count}건은 매우 잦음 — 내부 사람들이 적극적으로 움직이는 중`;
}
