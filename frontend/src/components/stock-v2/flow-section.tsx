"use client";

import type { Flow } from "@/types/card";
import { SectionShell } from "./section-shell";

/**
 * 수급 섹션 (KR-only).
 *
 * Backend: pykrx KRX 공식 일별 데이터 (외국인/기관 5거래일 누적 순매수 +
 * 연속 일수). Codex 시니어 트레이더 리뷰 권고(2026-05-14): KR retail
 * 매매 판단에 market sponsorship 은 절대 빠지면 안 되는 신호.
 *
 * 공매도(잔고/회전)는 2026-05-14 사용자 결정으로 drop — 가족 비전공자
 * 의사결정에 nuanced + noise > signal.
 *
 * UI 카피 가이드(memory: feedback_card_user_facing_copy):
 * - "외국인 순매수 120억" → "외국인이 최근 5일 동안 120억원 순매수
 *    (사들이고 있음)"
 * - "5일 연속" → "5일 연속 순매수"
 */
export function FlowSection({ flow }: { flow: Flow }) {
  const compact = buildCompact(flow);
  return (
    <SectionShell
      emoji="💰"
      title="수급 (외국인·기관)"
      compact={<span>{compact}</span>}
      expanded={<FlowExpanded flow={flow} />}
      helpText={
        <div className="space-y-1.5">
          <p>
            <strong>외국인·기관 투자자가 최근 5거래일 동안 얼마 사고 팔았는지</strong>.
            한국 retail 매매 판단의 baseline — "외국인이 사들이는 종목"인지 "팔고
            있는 종목"인지 한눈에.
          </p>
          <ul className="ml-3 space-y-0.5 list-disc">
            <li><strong>양수</strong> = 순매수 (사들이는 중) — 보통 긍정 신호</li>
            <li><strong>음수</strong> = 순매도 (팔고 있음) — 보통 부정 신호</li>
            <li><strong>5일 연속 순매수</strong> 같은 연속 일수 = 추세의 강도</li>
            <li>5일 동안 <strong>1억원 미만</strong>은 의미 있는 매매 신호 아님</li>
          </ul>
          <p className="text-[var(--surface-text-muted)] mt-1">
            출처: KRX 공식 일별 거래대금 (한국거래소).
          </p>
        </div>
      }
    />
  );
}

function buildCompact(flow: Flow): string {
  const parts: string[] = [];
  if (flow.foreign_net_5d_krw != null) {
    parts.push(`외국인 ${signedKrwShort(flow.foreign_net_5d_krw)} (5일)`);
  }
  if (flow.inst_net_5d_krw != null) {
    parts.push(`기관 ${signedKrwShort(flow.inst_net_5d_krw)} (5일)`);
  }
  return parts.length > 0 ? parts.join(" · ") : "수급 데이터 없음";
}

function FlowExpanded({ flow }: { flow: Flow }) {
  const rows: { label: string; value: string; help?: string }[] = [];

  if (flow.foreign_net_5d_krw != null) {
    const v = flow.foreign_net_5d_krw;
    const streak = flow.foreign_streak_days;
    rows.push({
      label: "외국인 — 최근 5거래일 순매수",
      value: signedKrw(v),
      help: flowHelp("외국인", v, streak),
    });
  }
  if (flow.inst_net_5d_krw != null) {
    const v = flow.inst_net_5d_krw;
    const streak = flow.inst_streak_days;
    rows.push({
      label: "기관 — 최근 5거래일 순매수",
      value: signedKrw(v),
      help: flowHelp("기관", v, streak),
    });
  }

  if (rows.length === 0) {
    return (
      <p className="text-sm text-[var(--surface-text-muted)]">
        수급 데이터 없음
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <dl className="space-y-1.5 text-xs">
        {rows.map((r) => (
          <div key={r.label} className="grid grid-cols-[1fr_auto] gap-x-3">
            <dt className="text-[var(--surface-text-muted)]">{r.label}</dt>
            <dd className="tabular-nums font-medium">{r.value}</dd>
            {r.help ? (
              <dd className="col-span-2 text-[11px] text-[var(--surface-text-subtle)]">
                → {r.help}
              </dd>
            ) : null}
          </div>
        ))}
      </dl>
      {flow.as_of ? (
        <p className="text-[11px] italic text-[var(--surface-text-subtle)]">
          출처: KRX 공식 ({flow.as_of} 기준)
        </p>
      ) : null}
    </div>
  );
}

function flowHelp(actor: string, netKrw: number, streak: number): string {
  const absM = Math.abs(netKrw);
  if (absM < 100_000_000) {
    return `의미 있는 매매 신호 아님 (5일 동안 1억원 미만)`;
  }
  const direction = netKrw > 0 ? "사들이는 중" : "팔고 있음";
  const streakNote =
    streak >= 3
      ? ` · ${streak}일 연속 순매수`
      : streak <= -3
      ? ` · ${Math.abs(streak)}일 연속 순매도`
      : "";
  return `${actor}이 ${direction}${streakNote}`;
}

function signedKrw(krw: number): string {
  const sign = krw >= 0 ? "+" : "−";
  const abs = Math.abs(krw);
  if (abs >= 1e12) return `${sign}${(abs / 1e12).toFixed(2)}조원`;
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(0)}억원`;
  return `${sign}${abs.toLocaleString()}원`;
}

function signedKrwShort(krw: number): string {
  const sign = krw >= 0 ? "+" : "−";
  const abs = Math.abs(krw);
  if (abs >= 1e12) return `${sign}${(abs / 1e12).toFixed(1)}조`;
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(0)}억`;
  return `${sign}${abs.toLocaleString()}`;
}
