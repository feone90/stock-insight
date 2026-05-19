"use client";

import { Activity } from "lucide-react";
import type { TechMomentum } from "@/types/card";
import { SectionShell } from "./section-shell";

/**
 * "최근 흐름" 섹션 — 옛 이름 "모멘텀 / 기술".
 *
 * 2026-05-14 사용자 피드백: 약어(RSI/MFI/CMF/OBV/RVOL/MA/ATR) 줄줄이는
 * 가족 비전공자에게 무의미. 모든 약어 풀어쓰고 한 줄 해석 동반.
 * SectionShell helpText 로 "최근 흐름이 무엇인지" 가족 친화 설명.
 *
 * feedback_card_user_facing_copy.md 카피 룰 적용.
 */

const HELP_TEXT = (
  <div className="space-y-2">
    <p>
      <strong>최근 주가가 어떻게 움직였는지 + 왜 그렇게 움직였는지</strong>를 숫자로 본 것.
      가격만 보면 올랐다/내렸다만 보이지만, 거래량·변동폭·평균선까지 같이 보면
      <em> 추세가 강한지 약한지 / 단기적으로 과열인지 과매도인지</em>까지 판별할 수 있어요.
    </p>
    <ul className="ml-3 space-y-0.5 list-disc">
      <li><strong>사려는 힘 vs 팔리는 힘 (옛 RSI)</strong> — 70 이상 = 단기 과열, 30 이하 = 단기 과매도</li>
      <li><strong>돈의 흐름 강도 (옛 CMF)</strong> — 양수 = 돈이 들어오는 중, 음수 = 빠지는 중</li>
      <li><strong>거래량 추세 (옛 OBV)</strong> — 가격 오를 때 거래량이 함께 늘었나, 줄었나</li>
      <li><strong>이동평균 정렬 (옛 MA stack)</strong> — 정배열 = 단기·장기 평균 모두 상승, 역배열 = 하락</li>
      <li><strong>거래량 비율 (옛 RVOL)</strong> — 1보다 크면 평소보다 활발한 거래</li>
      <li><strong>변동폭 (옛 ATR)</strong> — 하루 평균 몇 % 움직이는지</li>
    </ul>
  </div>
);

export function TechMomentumSection({ technical }: { technical: TechMomentum }) {
  const compact = buildCompact(technical);
  return (
    <SectionShell
      icon={<Activity size={17} />}
      title="최근 흐름"
      compact={<span>{compact}</span>}
      expanded={<TechExpanded tech={technical} />}
      helpText={HELP_TEXT}
    />
  );
}

function buildCompact(t: TechMomentum): string {
  const parts: string[] = [];
  if (t.rsi_14 != null) parts.push(rsiPhrase(t.rsi_14));
  if (t.ma_stack) parts.push(maStackPhrase(t.ma_stack));
  if (t.rvol_20 != null) parts.push(rvolPhrase(t.rvol_20));
  return parts.length > 0 ? parts.join(" · ") : t.summary_line || "지표 데이터 부족";
}

function TechExpanded({ tech }: { tech: TechMomentum }) {
  // 카피 가이드: 약어 절대 노출 X, 값 + 한 줄 해석 + (선택) 옛 약어 괄호.
  const rows: { label: string; value: string; help: string }[] = [];

  if (tech.rsi_14 != null) {
    rows.push({
      label: "사려는 힘 vs 팔리는 힘",
      value: tech.rsi_14.toFixed(0),
      help: rsiHelp(tech.rsi_14),
    });
  }
  if (tech.mfi_14 != null) {
    rows.push({
      label: "돈이 들어오는 힘 (거래량 포함)",
      value: tech.mfi_14.toFixed(0),
      help: rsiHelp(tech.mfi_14), // MFI도 0-100 같은 의미
    });
  }
  if (tech.cmf_20 != null) {
    rows.push({
      label: "돈의 흐름 강도",
      value: tech.cmf_20.toFixed(2),
      help: cmfHelp(tech.cmf_20),
    });
  }
  if (tech.obv_ratio != null) {
    rows.push({
      label: "거래량 누적 추세",
      value: tech.obv_ratio.toFixed(2),
      help: obvHelp(tech.obv_ratio),
    });
  }
  if (tech.ma_stack) {
    rows.push({
      label: "이동평균 정렬",
      value: tech.ma_stack,
      help: maStackHelp(tech.ma_stack),
    });
  }
  if (tech.rvol_20 != null) {
    rows.push({
      label: "거래량 (평소 대비)",
      value: `${tech.rvol_20.toFixed(1)}배`,
      help: rvolHelp(tech.rvol_20),
    });
  }
  if (tech.atr_pct != null) {
    rows.push({
      label: "하루 평균 변동폭",
      value: `${tech.atr_pct.toFixed(2)}%`,
      help: atrHelp(tech.atr_pct),
    });
  }
  if (tech.box_position) {
    rows.push({
      label: "박스권 위치",
      value: tech.box_position,
      help: "최근 60일 최저~최고 사이에서 지금 어디쯤 — 높을수록 최근 고가 근처",
    });
  }

  return (
    <div className="space-y-2 text-sm">
      {tech.summary_line ? (
        <p className="text-xs text-[var(--surface-text-muted)] leading-relaxed">
          {tech.summary_line}
        </p>
      ) : null}
      {rows.length === 0 ? (
        <p className="text-[var(--surface-text-muted)]">지표 데이터 부족</p>
      ) : (
        <dl className="space-y-1.5 text-xs">
          {rows.map((r) => (
            <div key={r.label} className="grid grid-cols-[1fr_auto] gap-x-3">
              <dt className="text-[var(--surface-text-muted)]">{r.label}</dt>
              <dd className="tabular-nums font-medium">{r.value}</dd>
              <dd className="col-span-2 text-[11px] text-[var(--surface-text-subtle)]">
                → {r.help}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

// ── 가족 친화 해석 helpers ──────────────────────────────────────────────

function rsiPhrase(rsi: number): string {
  if (rsi >= 70) return "사려는 힘 과열";
  if (rsi <= 30) return "팔리는 힘 과열";
  return `사고팔기 균형 (${rsi.toFixed(0)})`;
}

function rsiHelp(rsi: number): string {
  if (rsi >= 70) return "단기 과열 — 사람들이 너무 많이 사서 조정 가능성";
  if (rsi >= 60) return "사려는 힘 우세 — 상승 추세 안정";
  if (rsi <= 30) return "단기 과매도 — 너무 많이 팔려서 반등 가능성";
  if (rsi <= 40) return "팔리는 힘 우세 — 하락 압력";
  return "사고팔기 비슷 — 방향성 약함";
}

function cmfHelp(cmf: number): string {
  if (cmf >= 0.2) return "돈이 강하게 들어오는 중 — 매집 신호";
  if (cmf > 0) return "돈이 살짝 들어오는 중";
  if (cmf <= -0.2) return "돈이 강하게 빠지는 중 — 분배 신호";
  if (cmf < 0) return "돈이 살짝 빠지는 중";
  return "돈의 흐름 중립";
}

function obvHelp(obv: number): string {
  if (obv >= 1.2) return "거래량이 가격 상승을 뒷받침 — 상승 추세 신뢰도 ↑";
  if (obv <= 0.8) return "거래량 약함 — 가격 움직임 뒷받침 부족";
  return "거래량 추세 평범";
}

function maStackPhrase(stack: string): string {
  if (stack === "정배열") return "정배열 (상승 추세)";
  if (stack === "역배열") return "역배열 (하락 추세)";
  return "혼조";
}

function maStackHelp(stack: string): string {
  if (stack === "정배열") return "단기·중기·장기 평균이 위에서부터 순서대로 = 상승 흐름";
  if (stack === "역배열") return "장기·중기·단기 평균이 위에서부터 순서대로 = 하락 흐름";
  return "평균선이 엉켜있어 추세 불분명";
}

function rvolPhrase(rvol: number): string {
  if (rvol >= 1.5) return `거래 활발 (${rvol.toFixed(1)}배)`;
  if (rvol <= 0.7) return `거래 한산 (${rvol.toFixed(1)}배)`;
  return `거래 보통 (${rvol.toFixed(1)}배)`;
}

function rvolHelp(rvol: number): string {
  if (rvol >= 2) return "평소보다 2배 이상 거래 — 큰 뉴스나 자금 유입 가능성";
  if (rvol >= 1.5) return "평소보다 활발 — 관심도 증가";
  if (rvol <= 0.5) return "평소보다 한산 — 관심도 낮음";
  return "평소와 비슷한 거래량";
}

function atrHelp(atr: number): string {
  if (atr >= 5) return "변동성 매우 큼 — 단기 매매 위험";
  if (atr >= 3) return "변동성 큰 편";
  if (atr <= 1) return "변동성 작음 — 안정적";
  return "변동성 보통";
}
