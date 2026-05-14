"use client";

import type { AnalystRating, Earnings } from "@/types/card";
import { SectionShell } from "./section-shell";

/**
 * US-only — 다음 실적 발표 D-N + 분석가 매수/보유/매도 의견 분포.
 *
 * Codex priority 4 (2026-05-14): earnings 시점이 매매 판단 timing 의 핵심,
 * analyst consensus 가 sentiment baseline. 둘 다 Finnhub free tier 에서 옴.
 *
 * 카드 UI 카피 가이드(memory: feedback_card_user_facing_copy):
 * - "EPS estimate $2.45" → "주당이익 예상 2.45달러"
 * - "BMO" → "장 시작 전"
 * - "buy 8 / hold 3 / sell 1" → "전문가 12명: 매수 8 / 보유 3 / 매도 1
 *    → 다수 의견 매수 우세"
 */
export function EarningsAnalystSection({
  earnings,
  rating,
}: {
  earnings: Earnings | null | undefined;
  rating: AnalystRating | null | undefined;
}) {
  const compact = buildCompact(earnings, rating);
  return (
    <SectionShell
      emoji="🗓️"
      title="실적·분석가 의견"
      compact={<span>{compact}</span>}
      expanded={<ExpandedBody earnings={earnings} rating={rating} />}
      helpText={
        <div className="space-y-1.5">
          <p>
            <strong>다음 분기 실적 발표까지 며칠 + 전문가들의 매수/보유/매도
            의견 분포</strong>.
          </p>
          <ul className="ml-3 space-y-0.5 list-disc">
            <li><strong>실적 발표 D-N</strong> — 발표일까지 N일 남음. 발표 전후엔 주가 변동성 커지는 게 일반적</li>
            <li><strong>주당이익 예상</strong> — 전문가들이 이번 분기 1주당 얼마 벌 거라고 추정. 발표값이 이보다 높으면 보통 주가 상승</li>
            <li><strong>매수 N명 · 보유 N명 · 매도 N명</strong> — 전문가 N명의 의견 분포. 매수 우세면 긍정 sentiment</li>
          </ul>
          <p className="text-[var(--surface-text-muted)] mt-1">
            US 종목만. 출처: Finnhub (이메일 가입 무료). KR 종목은 별도 출처 (추후).
          </p>
        </div>
      }
    />
  );
}

function buildCompact(
  earnings: Earnings | null | undefined,
  rating: AnalystRating | null | undefined,
): string {
  const parts: string[] = [];
  if (earnings?.date) {
    if (earnings.days_until >= 0) {
      parts.push(`다음 실적 D-${earnings.days_until}`);
    } else {
      parts.push(`실적 발표 ${Math.abs(earnings.days_until)}일 전`);
    }
  }
  if (rating) {
    const total = analystTotal(rating);
    if (total > 0) {
      parts.push(`분석가 ${total}명 · 매수 ${rating.buy + rating.strong_buy}`);
    }
  }
  return parts.length > 0 ? parts.join(" · ") : "실적·분석가 데이터 없음";
}

function ExpandedBody({
  earnings,
  rating,
}: {
  earnings: Earnings | null | undefined;
  rating: AnalystRating | null | undefined;
}) {
  return (
    <div className="space-y-3 text-xs">
      {earnings ? <EarningsBlock earnings={earnings} /> : null}
      {rating ? <RatingBlock rating={rating} /> : null}
      {!earnings && !rating ? (
        <p className="text-sm text-[var(--surface-text-muted)]">
          실적·분석가 데이터 없음 (Finnhub 키 미설정이거나 종목 미지원)
        </p>
      ) : null}
    </div>
  );
}

function EarningsBlock({ earnings }: { earnings: Earnings }) {
  const ddayLine =
    earnings.days_until >= 0
      ? `다음 실적 발표까지 ${earnings.days_until}일 남음 (${humanDate(
          earnings.date,
        )})`
      : `실적 발표 ${Math.abs(earnings.days_until)}일 전 (${humanDate(
          earnings.date,
        )})`;
  return (
    <div className="space-y-1">
      <p className="font-medium">📊 실적 발표</p>
      <p className="text-[var(--surface-text-muted)]">{ddayLine}</p>
      {earnings.hour ? (
        <p className="text-[11px] text-[var(--surface-text-subtle)]">
          → 발표 시점: {hourKr(earnings.hour)}
        </p>
      ) : null}
      {earnings.eps_estimate != null ? (
        <p className="text-[11px] text-[var(--surface-text-subtle)]">
          → 주당이익 예상 {earnings.eps_estimate.toFixed(2)}달러
        </p>
      ) : null}
      {earnings.revenue_estimate != null ? (
        <p className="text-[11px] text-[var(--surface-text-subtle)]">
          → 매출 예상 {formatUsdShort(earnings.revenue_estimate)}
        </p>
      ) : null}
    </div>
  );
}

function RatingBlock({ rating }: { rating: AnalystRating }) {
  const buyTotal = rating.buy + rating.strong_buy;
  const sellTotal = rating.sell + rating.strong_sell;
  const total = analystTotal(rating);
  const verdict = analystVerdict(buyTotal, rating.hold, sellTotal);
  return (
    <div className="space-y-1">
      <p className="font-medium">👥 분석가 의견 ({rating.month})</p>
      <p className="text-[var(--surface-text-muted)]">
        전문가 {total}명 ·
        <span className="text-red-600 dark:text-red-400"> 매수 {buyTotal}</span> /
        <span className="text-amber-600 dark:text-amber-400"> 보유 {rating.hold}</span> /
        <span className="text-blue-600 dark:text-blue-400"> 매도 {sellTotal}</span>
      </p>
      <p className="text-[11px] text-[var(--surface-text-subtle)]">→ {verdict}</p>
    </div>
  );
}

function analystTotal(r: AnalystRating): number {
  return r.buy + r.hold + r.sell + r.strong_buy + r.strong_sell;
}

function analystVerdict(buy: number, hold: number, sell: number): string {
  const total = buy + hold + sell;
  if (total === 0) return "의견 없음";
  const buyPct = (buy / total) * 100;
  const sellPct = (sell / total) * 100;
  if (buyPct >= 70) return "다수 의견이 매수 — 강한 긍정";
  if (buyPct >= 50) return "매수 의견 우세";
  if (sellPct >= 50) return "매도 의견 우세 — 주의";
  if (sellPct >= 30) return "매도 의견 적지 않음 — 의견 갈림";
  return "의견 갈림 (보유 우세)";
}

function hourKr(h: string): string {
  if (h === "bmo") return "장 시작 전";
  if (h === "amc") return "장 마감 후";
  if (h === "dmh") return "장 중";
  return h;
}

function humanDate(iso: string): string {
  try {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString("ko-KR");
  } catch {
    return iso;
  }
}

function formatUsdShort(usd: number): string {
  if (usd >= 1e9) return `${(usd / 1e9).toFixed(1)}B달러`;
  if (usd >= 1e6) return `${(usd / 1e6).toFixed(0)}M달러`;
  return `$${usd.toLocaleString()}`;
}
