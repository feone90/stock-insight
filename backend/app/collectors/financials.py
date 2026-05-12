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


def _yf_market_cap(ticker: str, market: str | None) -> int | None:  # pragma: no cover
    """yfinance .KS/.KQ market_cap fallback. stock.market_cap이 None인 신규
    universe 종목들 자체적으로 보강.
    """
    import yfinance as yf

    if market == "KOSPI":
        suffixes = (".KS",)
    elif market == "KOSDAQ":
        suffixes = (".KQ",)
    else:
        suffixes = (".KS", ".KQ")
    for sfx in suffixes:
        try:
            mc = yf.Ticker(f"{ticker}{sfx}").info.get("marketCap")
        except Exception:
            continue
        if mc:
            return int(mc)
    return None


def fetch_kr_financials_raw(ticker: str, market: str | None) -> dict:  # pragma: no cover
    """dartlab analysis('financial', '수익성') + yfinance market_cap 보강."""
    import dartlab

    out: dict = {"margin": [], "return": [], "market_cap": None}
    try:
        c = dartlab.Company(ticker)
        if c.market == "KR":
            prof = c.analysis("financial", "수익성") or {}
            out["margin"] = (prof.get("marginTrend") or {}).get("history") or []
            out["return"] = (prof.get("returnTrend") or {}).get("history") or []
    except Exception as e:
        logger.warning("dartlab fetch failed for %s: %s", ticker, e)
    # market_cap fallback — Stock.market_cap이 None인 신규 universe 종목 대응.
    out["market_cap"] = _yf_market_cap(ticker, market)
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
    margin = _latest_fully_populated(
        margin_rows, ("revenue", "operatingIncome", "netIncome")
    )
    if not margin:
        return None
    period = margin.get("period")
    # 같은 period 의 returnTrend row 매칭 — equity / totalAssets / roe 가져온다.
    ret = next((r for r in return_rows if r.get("period") == period), {})

    revenue_won = int(margin["revenue"] * _KR_UNIT_TO_WON)
    op_won = int(margin["operatingIncome"] * _KR_UNIT_TO_WON)
    net_won = int(margin["netIncome"] * _KR_UNIT_TO_WON)
    equity_won = int(ret.get("equity") * _KR_UNIT_TO_WON) if ret.get("equity") else None

    # market_cap: fresh yfinance > stock 테이블. write-back 으로 stock 의 시총
    # 컬럼도 갱신해 다음 sync 호출에서 재활용.
    fresh_mc = raw.get("market_cap")
    if fresh_mc:
        stock.market_cap = fresh_mc
        market_cap = fresh_mc
    elif stock.market_cap:
        market_cap = int(stock.market_cap)
    else:
        market_cap = None
    logger.info(
        "kr_values[%s] period=%s fresh_mc=%s stock_mc=%s net=%s equity=%s",
        stock.ticker, period, fresh_mc, stock.market_cap, net_won, equity_won,
    )

    per = round(market_cap / net_won, 2) if (market_cap and net_won > 0) else None
    pbr = round(market_cap / equity_won, 2) if (market_cap and equity_won and equity_won > 0) else None
    # dartlab ROE 우선, 없으면 직접 계산.
    roe = ret.get("roe")
    if roe is None and equity_won and equity_won > 0:
        roe = round(net_won / equity_won * 100, 2)
    elif roe is not None:
        roe = round(roe, 2)

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
        "dividend_yield": None,  # dartlab analysis 에 표면화 안 됨 — Phase B 에서 capital() 사용
        "market_cap": market_cap,
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
            label = "DART"
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
