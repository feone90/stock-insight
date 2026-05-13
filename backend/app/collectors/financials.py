"""재무 데이터 동기화.

KR (KOSPI/KOSDAQ/KRX) : dartlab `analysis("financial", "수익성")` 로
  matrintTrend + returnTrend annual history 파싱 → 매출/영업이익/순이익/자본/총자산.
  PER/PBR/ROE 는 market_cap 과 결합해 직접 계산.

US (NYSE/NASDAQ/NMS/NYQ/AMEX) : yfinance `Ticker(symbol).info` TTM.

"latest fully-populated" 연도를 골라 한 row 쓴다 — 2025/2024 사업보고서가
아직 제출되지 않은 시점에는 2023이 가장 최근 완성치.
"""

import asyncio
import logging
from datetime import date

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.markets import is_kr
from app.models import Stock
from app.models.financial import Financial

logger = logging.getLogger(__name__)

# DART rawFinance/analysis 모두 "백만원" 단위. 우리 Financial 테이블은 원 단위로
# 저장 (yfinance US 와 일관성 유지).
_KR_UNIT_TO_WON = 1_000_000


# ---------- US: yfinance ----------


def fetch_us_financials(ticker: str) -> dict:  # pragma: no cover
    import yfinance as yf

    try:
        info = yf.Ticker(ticker).info
    except Exception:
        return {}
    if not info:
        return {}
    return info


def _us_values(stock: Stock, info: dict, period: str) -> dict | None:
    if not info.get("marketCap") and not info.get("totalRevenue"):
        return None
    roe = info.get("returnOnEquity")
    div_yield = info.get("dividendYield")
    return {
        "stock_id": stock.id,
        "period": period,
        "period_type": "ttm",
        "revenue": int(info["totalRevenue"]) if info.get("totalRevenue") else None,
        "operating_profit": int(info["operatingIncome"]) if info.get("operatingIncome") else None,
        "net_income": int(info["netIncome"]) if info.get("netIncome") else None,
        "per": info.get("trailingPE"),
        "pbr": info.get("priceToBook"),
        "roe": round(roe * 100, 2) if roe else None,
        "dividend_yield": round(div_yield * 100, 2) if div_yield else None,
        "market_cap": info.get("marketCap"),
    }


# ---------- KR: dartlab DART ----------


def _yf_kr_ratios(ticker: str, market: str | None) -> dict:  # pragma: no cover
    """yfinance .KS/.KQ 에서 KR fallback ratios. dartlab 이 IS roll-up 못 만드는
    종목 (예: 인보사 사태 이후 코오롱티슈진 — DART 사업보고서 부재) 도 yfinance
    가 marketCap/sharesOutstanding 만큼은 줄 때가 있어 카드의 최소 정보를 살린다.
    """
    import yfinance as yf

    if market == "KOSPI":
        suffixes = (".KS",)
    elif market == "KOSDAQ":
        suffixes = (".KQ",)
    else:
        suffixes = (".KS", ".KQ")
    out: dict = {
        "market_cap": None,
        "trailing_pe": None,
        "price_to_book": None,
        "dividend_yield": None,
        "shares_outstanding": None,
    }
    for sfx in suffixes:
        try:
            info = yf.Ticker(f"{ticker}{sfx}").info
        except Exception:
            continue
        mc = info.get("marketCap")
        if not mc:
            continue
        out["market_cap"] = int(mc)
        out["trailing_pe"] = info.get("trailingPE")
        out["price_to_book"] = info.get("priceToBook")
        dy = info.get("dividendYield")
        out["dividend_yield"] = round(dy * 100, 2) if dy else None
        out["shares_outstanding"] = info.get("sharesOutstanding")
        break
    return out


def fetch_kr_financials_raw(ticker: str, market: str | None) -> dict:  # pragma: no cover
    """dartlab analysis('financial', '수익성') + yfinance ratios fallback."""
    import dartlab

    out: dict = {"margin": [], "return": [], "yf": {}}
    try:
        c = dartlab.Company(ticker)
        if c.market == "KR":
            prof = c.analysis("financial", "수익성") or {}
            out["margin"] = (prof.get("marginTrend") or {}).get("history") or []
            out["return"] = (prof.get("returnTrend") or {}).get("history") or []
    except Exception as e:
        logger.warning("dartlab fetch failed for %s: %s", ticker, e)
    out["yf"] = _yf_kr_ratios(ticker, market)
    return out


def _latest_fully_populated(rows: list[dict], required: tuple[str, ...]) -> dict | None:
    """가장 최신 연도 중 required 필드가 모두 채워진 row. 없으면 None."""
    # rows 는 dartlab 이 desc 정렬 (2025, 2024, 2023, ...) — 그대로 순회.
    for r in rows:
        if all(r.get(k) is not None for k in required):
            return r
    return None


def _kr_values(stock: Stock, raw: dict) -> dict | None:
    margin_rows = raw.get("margin") or []
    return_rows = raw.get("return") or []
    yf_fallback = raw.get("yf") or {}

    # market_cap: fresh yfinance > stock 테이블. write-back 으로 stock 의 시총
    # 컬럼도 갱신해 다음 sync 호출에서 재활용.
    fresh_mc = yf_fallback.get("market_cap")
    if fresh_mc:
        stock.market_cap = fresh_mc
        market_cap = fresh_mc
    elif stock.market_cap:
        market_cap = int(stock.market_cap)
    else:
        market_cap = None

    margin = _latest_fully_populated(
        margin_rows, ("revenue", "operatingIncome", "netIncome")
    )

    if margin:
        # dartlab IS roll-up 정상 — primary path.
        period = margin.get("period")
        ret = next((r for r in return_rows if r.get("period") == period), {})
        revenue_won = int(margin["revenue"] * _KR_UNIT_TO_WON)
        op_won = int(margin["operatingIncome"] * _KR_UNIT_TO_WON)
        net_won = int(margin["netIncome"] * _KR_UNIT_TO_WON)
        equity_won = int(ret.get("equity") * _KR_UNIT_TO_WON) if ret.get("equity") else None

        per = round(market_cap / net_won, 2) if (market_cap and net_won > 0) else None
        pbr = round(market_cap / equity_won, 2) if (market_cap and equity_won and equity_won > 0) else None
        roe = ret.get("roe")
        if roe is None and equity_won and equity_won > 0:
            roe = round(net_won / equity_won * 100, 2)
        elif roe is not None:
            roe = round(roe, 2)

        logger.info(
            "kr_values[%s] DART period=%s mc=%s net=%s equity=%s",
            stock.ticker, period, market_cap, net_won, equity_won,
        )
        return {
            "stock_id": stock.id,
            "period": f"{period}A",
            "period_type": "annual",
            "revenue": revenue_won,
            "operating_profit": op_won,
            "net_income": net_won,
            "per": per,
            "pbr": pbr,
            "roe": roe,
            "dividend_yield": yf_fallback.get("dividend_yield"),
            "market_cap": market_cap,
        }

    # DART 빈 결과 — 회계감리/거래정지/R&D 단계 종목 (예: 코오롱티슈진).
    # Codex review [medium]: stale stock.market_cap 을 "올해 yfinance 시총만"
    # 라벨로 카드에 박으면, 정작 데이터 깨진 종목에서 거짓말함. fresh yfinance
    # 응답이 있을 때만 yfinance-only Financial row 를 만든다. 그 외엔 None →
    # data_layer._fetch_fundamentals 가 stock.market_cap fallback path 로 가서
    # "시총만 — 재무 미수집 (분석 시작 전)" 라벨을 정직하게 노출.
    if not fresh_mc:
        logger.info(
            "kr_values[%s] no DART IS and no fresh yfinance — return None "
            "(data_layer will surface stock.market_cap as stale fallback)",
            stock.ticker,
        )
        return None
    logger.info(
        "kr_values[%s] yfinance-only mc=%s pe=%s pb=%s (DART IS empty, fresh yf)",
        stock.ticker, fresh_mc, yf_fallback.get("trailing_pe"), yf_fallback.get("price_to_book"),
    )
    return {
        "stock_id": stock.id,
        "period": f"{date.today().year}A",
        "period_type": "annual",
        "revenue": None,
        "operating_profit": None,
        "net_income": None,
        "per": yf_fallback.get("trailing_pe"),
        "pbr": yf_fallback.get("price_to_book"),
        "roe": None,
        "dividend_yield": yf_fallback.get("dividend_yield"),
        "market_cap": fresh_mc,
    }


# ---------- 통합 ----------


async def sync_financials(db: AsyncSession, stock: Stock) -> dict:
    """종목 시장에 따라 DART(KR) 또는 yfinance(US) 로 재무지표 동기화."""
    try:
        if is_kr(stock.market):
            raw = await asyncio.to_thread(
                fetch_kr_financials_raw, stock.ticker, stock.market
            )
            values = _kr_values(stock, raw)
            # primary path 가 dartlab annual row 였는지, yfinance fallback 이었는지
            # 응답에서 구분해 운영자가 종목별 데이터 출처 확인 가능.
            label = "DART" if values and values.get("revenue") is not None else "yfinance-KR"
        else:
            info = await asyncio.to_thread(fetch_us_financials, stock.ticker)
            values = _us_values(stock, info, f"{date.today().year}Q0")
            label = "yfinance"

        if not values:
            return {"financials_synced": 0, "error": f"재무 데이터 없음 ({label})"}

        update_values = {
            k: v for k, v in values.items() if k not in ("stock_id", "period", "period_type")
        }
        stmt = insert(Financial).values(**values).on_conflict_do_update(
            constraint="uq_financial_stock_period",
            set_=update_values,
        )
        await db.execute(stmt)
        await db.commit()
        return {
            "financials_synced": 1,
            "source": label,
            "period": values["period"],
            "per": values.get("per"),
            "pbr": values.get("pbr"),
            "roe": values.get("roe"),
            "market_cap": values.get("market_cap"),
            "revenue": values.get("revenue"),
            "net_income": values.get("net_income"),
        }

    except Exception as e:
        return {"financials_synced": 0, "error": f"재무지표 동기화 실패: {e}"}
