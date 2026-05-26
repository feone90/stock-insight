"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Brain,
  CandlestickChart,
  Clock3,
  FolderKanban,
  LineChart,
  Newspaper,
  Search,
  UserRound,
} from "lucide-react";
import { getFavorites } from "@/services/api";
import { onUserChanged } from "@/services/user";
import { currencyMark, isKRMarket } from "@/lib/markets";
import type { Stock } from "@/types/stock";

const RECOMMENDATIONS: { ticker: string; name: string; market: string; desc: string }[] = [
  { ticker: "005930", name: "삼성전자", market: "KOSPI", desc: "한국 대표 반도체" },
  { ticker: "000660", name: "SK하이닉스", market: "KOSPI", desc: "HBM 메모리 선두" },
  { ticker: "TSLA", name: "Tesla", market: "NASDAQ", desc: "AI · 전기차" },
];

export default function Home() {
  const [favorites, setFavorites] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(true);
  const [shortcut] = useState(getShortcutLabel);

  useEffect(() => {
    const reload = () => {
      setLoading(true);
      getFavorites()
        .then(setFavorites)
        .catch(console.error)
        .finally(() => setLoading(false));
    };
    reload();
    return onUserChanged(reload);
  }, []);

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 md:px-6 md:py-9">
      <HomeGuide shortcut={shortcut} favoriteCount={favorites.length} />

      {loading ? (
        <div className="mt-6 text-slate-500">로딩 중...</div>
      ) : favorites.length === 0 ? (
        <EmptyState shortcut={shortcut} />
      ) : (
        <section className="mt-7">
          <div className="mb-4 flex flex-col gap-3 border-t border-slate-800 pt-5 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-50">
                즐겨찾기 종목
              </h1>
              <p className="mt-1 text-sm text-slate-400">
                현재 선택한 사용자의 관심 종목입니다. 카드를 열면 차트, 뉴스/이슈,
                관계망, AI 판단을 한 화면에서 볼 수 있습니다.
              </p>
            </div>
            <Link
              href="/portfolio"
              className="inline-flex w-fit items-center gap-2 rounded-md border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-sm font-medium text-blue-100 transition-colors hover:bg-blue-500/15"
            >
              <FolderKanban size={15} />
              포트폴리오 전체 흐름
            </Link>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {favorites.map((stock) => (
              <Link
                key={stock.ticker}
                href={`/stock/${stock.ticker}`}
                className="group rounded-lg border border-slate-800 bg-slate-900 p-4 transition-colors hover:border-slate-600"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-semibold text-slate-50 group-hover:text-blue-400 transition-colors">
                      {stock.name}
                    </div>
                    <div className="text-sm text-slate-500">
                      {stock.ticker} · {stock.market}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-semibold text-slate-50">
                      {isKRMarket(stock.market) ? (
                        <>
                          {stock.current_price.toLocaleString()}
                          <span className="text-xs ml-0.5">원</span>
                        </>
                      ) : (
                        <>
                          {currencyMark(stock.market)}
                          {stock.current_price.toLocaleString()}
                        </>
                      )}
                    </div>
                    <div
                      className={`text-sm ${
                        stock.change_percent >= 0
                          ? "text-red-400"
                          : "text-blue-400"
                      }`}
                    >
                      {stock.change_percent >= 0 ? "▲" : "▼"}{" "}
                      {Math.abs(stock.change).toLocaleString()} (
                      {stock.change_percent >= 0 ? "+" : ""}
                      {stock.change_percent}%)
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function getShortcutLabel() {
  if (typeof navigator === "undefined") return "Ctrl+K";
  const platform =
    (navigator as Navigator & { userAgentData?: { platform?: string } })
      .userAgentData?.platform ||
    navigator.platform ||
    navigator.userAgent ||
    "";
  return /Mac|iPhone|iPad|iPod/i.test(platform) ? "⌘K" : "Ctrl+K";
}

function HomeGuide({
  shortcut,
  favoriteCount,
}: {
  shortcut: string;
  favoriteCount: number;
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-950/70">
      <div className="grid gap-0 lg:grid-cols-[1.05fr_0.95fr]">
        <div className="border-b border-slate-800 p-4 md:p-5 lg:border-b-0 lg:border-r">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase text-cyan-300">
                StockInsight 사용 기준
              </p>
              <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-50 md:text-3xl">
                처음엔 이 순서대로 보면 됩니다
              </h1>
            </div>
            <div className="rounded-lg border border-cyan-500/25 bg-cyan-500/10 px-3 py-2 text-right">
              <div className="text-[11px] text-cyan-200">내 관심종목</div>
              <div className="text-lg font-semibold text-slate-50">{favoriteCount}개</div>
            </div>
          </div>

          <div className="grid gap-2 sm:grid-cols-2">
            <GuideStep
              icon={<UserRound size={16} />}
              title="사용자 선택"
              body="오른쪽 위 사용자 메뉴에서 이름을 추가하거나 전환하면 즐겨찾기가 사람별로 분리됩니다."
            />
            <GuideStep
              icon={<Search size={16} />}
              title="종목 검색"
              body={`${shortcut} 또는 상단 검색창에서 국내/미국 종목을 찾고 카드에서 즐겨찾기에 추가합니다.`}
            />
            <GuideStep
              icon={<FolderKanban size={16} />}
              title="포트폴리오"
              body="국내장을 먼저, 미국장을 다음에 묶고 가격 변동·AI 판단·뉴스·관계 신호로 우선순위를 정합니다."
            />
            <GuideStep
              icon={<CandlestickChart size={16} />}
              title="종목 카드"
              body="차트, 과거 이벤트 키워드, 관계망, 뉴스/이슈, 매크로, 펀더멘털, 의사결정을 함께 봅니다."
            />
          </div>
        </div>

        <div className="p-4 md:p-5">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-100">
            <Clock3 size={16} className="text-amber-300" />
            자동 갱신 시간은 모두 한국시간 기준
          </div>
          <div className="grid gap-2">
            <RefreshRow
              label="한국장 가격"
              value="09:10 · 15:40"
              detail="개장 직후와 마감 직후 가격만 빠르게 갱신"
            />
            <RefreshRow
              label="미국장 가격"
              value="22:35 · 다음날 05:05"
              detail="미국장 개장/마감에 맞춰 자동 보정, 화면 표기는 한국시간"
            />
            <RefreshRow
              label="전체 데이터"
              value="08:00 · 18:00"
              detail="즐겨찾기 종목 합집합 기준 가격·재무·뉴스·공시 동기화"
            />
            <RefreshRow
              label="AI 카드"
              value="국내 08:30/16:00 · 미국 07:00/22:30"
              detail="같은 종목을 여러 사용자가 담아도 1번만 분석, 오래된 카드 우선"
            />
          </div>

          <div className="mt-4 grid gap-2 sm:grid-cols-3">
            <MiniRule
              icon={<LineChart size={15} />}
              title="장중 가격"
              body="종목 페이지가 열려 있으면 장중 30초마다 가격만 갱신합니다."
            />
            <MiniRule
              icon={<Newspaper size={15} />}
              title="뉴스·공시"
              body="새 이슈가 있으면 AI 의견 갱신 후보가 됩니다."
            />
            <MiniRule
              icon={<Brain size={15} />}
              title="전체 새로고침"
              body="가격 → 뉴스·공시 → AI 의견 순서로 실행됩니다."
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function GuideStep({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-100">
        <span className="inline-flex size-7 items-center justify-center rounded-md border border-slate-700 bg-slate-950 text-cyan-200">
          {icon}
        </span>
        {title}
      </div>
      <p className="text-xs leading-relaxed text-slate-400">{body}</p>
    </div>
  );
}

function RefreshRow({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="grid gap-2 rounded-lg border border-slate-800 bg-slate-900/60 p-3 sm:grid-cols-[120px_1fr] sm:items-center">
      <div className="text-xs font-medium text-slate-400">{label}</div>
      <div>
        <div className="text-sm font-semibold text-slate-50">{value}</div>
        <div className="mt-0.5 text-xs text-slate-500">{detail}</div>
      </div>
    </div>
  );
}

function MiniRule({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
      <div className="mb-1.5 flex items-center gap-2 text-xs font-semibold text-slate-100">
        <span className="text-amber-300">{icon}</span>
        {title}
      </div>
      <p className="text-[11px] leading-relaxed text-slate-500">{body}</p>
    </div>
  );
}

function EmptyState({ shortcut }: { shortcut: string }) {
  return (
    <div className="mt-7 space-y-7 border-t border-slate-800 pt-5">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-[var(--surface-text)]">
          처음 보시나요?
        </h1>
        <p className="mt-3 text-sm text-[var(--surface-text-muted)] leading-relaxed">
          <kbd className="inline-flex items-center gap-1 text-xs border border-[var(--surface-border)] rounded px-1.5 py-0.5 font-mono text-[var(--surface-text)]">
            {shortcut}
          </kbd>
          {"  "}로 종목을 검색하면 카드가 자동으로 생성됩니다. 아래 종목으로 빠르게 시작해보세요.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {RECOMMENDATIONS.map((s) => (
          <Link
            key={s.ticker}
            href={`/stock/${s.ticker}`}
            className="group rounded-xl border border-[var(--surface-border)] bg-[var(--surface-card)] p-4 transition-colors hover:border-blue-500/40"
          >
            <div className="font-semibold text-[var(--surface-text)] group-hover:text-blue-400 transition-colors">
              {s.name}
            </div>
            <div className="mt-1 text-xs font-mono text-[var(--surface-text-muted)]">
              {s.ticker} · {s.market}
            </div>
            <div className="mt-2 text-xs text-[var(--surface-text-muted)]">
              {s.desc}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
