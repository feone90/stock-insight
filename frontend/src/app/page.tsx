"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Clock3,
  FolderKanban,
  LineChart,
  Newspaper,
  RotateCw,
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
    <section className="overflow-hidden rounded-2xl border border-slate-800 bg-[linear-gradient(135deg,rgba(2,6,23,0.98),rgba(15,23,42,0.92))]">
      <div className="border-b border-slate-800 px-4 py-4 md:px-5 md:py-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-300">
              관심종목 운영판
            </p>
            <h1 className="mt-2 text-[27px] font-semibold leading-tight tracking-tight text-slate-50 md:text-4xl">
              즐겨찾기만 정하면 가격과 뉴스, AI 판단이 자동 갱신됩니다.
            </h1>
            <p className="mt-3 text-sm leading-relaxed text-slate-400">
              상단에서 사용자를 고르고 종목을 추가하세요. 포트폴리오는 전체 우선순위, 종목 카드는 판단 근거를 보여줍니다.
            </p>
          </div>
          <div className="grid grid-cols-3 overflow-hidden rounded-xl border border-slate-700/80 bg-slate-950/70 text-center">
            <Metric label="내 관심종목" value={`${favoriteCount}개`} />
            <Metric label="중복 분석" value="종목당 1회" />
            <Metric label="표기 시간" value="한국시간" />
          </div>
        </div>
      </div>

      <div className="grid gap-0 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="border-b border-slate-800 p-4 md:p-5 lg:border-b-0 lg:border-r">
          <h2 className="text-sm font-semibold text-slate-100">어디서 무엇을 보나</h2>
          <ol className="mt-4 space-y-3">
            <GuideStep
              icon={<UserRound size={15} />}
              title="사용자"
              body="오른쪽 위 메뉴에서 이름을 추가하거나 전환합니다. 즐겨찾기는 사용자별로 따로 저장됩니다."
            />
            <GuideStep
              icon={<Search size={15} />}
              title="종목 추가"
              body={`${shortcut} 또는 상단 검색창에서 국내/미국 종목을 찾고, 카드의 별 버튼으로 관심종목에 넣습니다.`}
            />
            <GuideStep
              icon={<FolderKanban size={15} />}
              title="포트폴리오"
              body="국내장 먼저, 미국장 다음으로 묶고 가격 변동, AI 판단, 뉴스, 관계 신호를 기준으로 정렬합니다."
            />
          </ol>
          <div className="mt-5 rounded-xl border border-cyan-500/20 bg-cyan-500/[0.06] p-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-cyan-100">
              <LineChart size={15} />
              종목 카드는 근거를 확인하는 곳
            </div>
            <p className="mt-2 text-xs leading-relaxed text-cyan-100/70">
              차트 이벤트 키워드, 관계망, 뉴스/이슈, 매크로, 펀더멘털, 최근 흐름, 의사결정을 한 화면에서 확인합니다.
            </p>
          </div>
        </div>

        <div className="p-4 md:p-5">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <Clock3 size={16} className="text-amber-300" />
            자동 갱신 시간표
          </div>
          <div className="mt-4 divide-y divide-slate-800 overflow-hidden rounded-xl border border-slate-800 bg-slate-950/40">
            <RefreshRow
              label="한국장 가격"
              value="09:10 / 15:40"
              detail="개장 직후와 마감 직후 가격만 갱신"
            />
            <RefreshRow
              label="미국장 가격"
              value="22:35 / 다음날 05:05"
              detail="미국장 개장/마감 기준, 화면 표기는 한국시간"
            />
            <RefreshRow
              label="전체 데이터"
              value="08:00 / 18:00"
              detail="즐겨찾기 종목 합집합의 가격·재무·뉴스·공시 동기화"
            />
            <RefreshRow
              label="AI 카드"
              value="국내 08:30·16:00 / 미국 07:00·22:30"
              detail="같은 종목은 사용자 수와 관계없이 1번만 분석"
            />
          </div>

          <div className="mt-4 grid gap-2 sm:grid-cols-3">
            <MiniRule icon={<LineChart size={15} />} title="장중 가격" body="종목 페이지가 열려 있으면 30초마다 가격만 갱신" />
            <MiniRule icon={<Newspaper size={15} />} title="뉴스·공시" body="새 이슈가 있으면 AI 의견 갱신 후보로 반영" />
            <MiniRule icon={<RotateCw size={15} />} title="전체 새로고침" body="가격, 뉴스·공시, AI 의견 순서로 실행" />
          </div>
        </div>
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 px-3 py-3">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-1 truncate text-base font-semibold text-slate-50">{value}</div>
    </div>
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
    <li className="grid grid-cols-[32px_1fr] gap-3">
      <span className="mt-0.5 inline-flex size-8 items-center justify-center rounded-md border border-slate-700 bg-slate-950 text-cyan-200">
        {icon}
      </span>
      <div>
        <div className="text-sm font-semibold text-slate-100">
          {title}
        </div>
        <p className="mt-1 text-xs leading-relaxed text-slate-400">{body}</p>
      </div>
    </li>
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
    <div className="grid gap-2 px-3 py-3 sm:grid-cols-[118px_1fr] sm:items-center">
      <div className="text-xs font-medium text-slate-500">{label}</div>
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
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3 transition-colors hover:border-slate-700">
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
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight text-[var(--surface-text)]">
          관심 종목을 추가하세요
        </h1>
        <p className="mt-3 text-sm text-[var(--surface-text-muted)] leading-relaxed">
          <kbd className="inline-flex items-center gap-1 text-xs border border-[var(--surface-border)] rounded px-1.5 py-0.5 font-mono text-[var(--surface-text)]">
            {shortcut}
          </kbd>
          {"  "}로 종목을 검색하면 분석 카드가 생성됩니다. 아래 종목으로 먼저 열어볼 수 있습니다.
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
