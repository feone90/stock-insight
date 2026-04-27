"""LLM chat agent tools — DB access functions.

Each tool opens its own async_session (same pattern as scheduler._sync_single_stock).
Returns dict on success, {"error": "..."} on known error. Never raises for expected errors.

`get_my_favorites` is special: the orchestrator injects user_id directly, the
LLM never sees or supplies it (no impersonation surface).
"""

import logging
from datetime import date, timedelta

from sqlalchemy import desc, select

from app.database import async_session
from app.models import (
    Disclosure,
    ExchangeRate,
    Favorite,
    Financial,
    PriceHistory,
    Stock,
)
from app.models.analysis import Analysis, KeywordDetail
from app.models.news import News

logger = logging.getLogger(__name__)

NEWS_CONTENT_SNIPPET_LEN = 400
DISCLOSURE_CONTENT_SNIPPET_LEN = 400


async def get_stock_snapshot(ticker: str) -> dict:
    """종목 기본정보 + 현재가 + 최신 분석 + 재무지표 — 단일 시점."""
    ticker = ticker.strip().upper()
    async with async_session() as db:
        stock_result = await db.execute(
            select(Stock).where(Stock.ticker == ticker)
        )
        stock = stock_result.scalar_one_or_none()
        if not stock:
            return {"error": f"종목 '{ticker}'을(를) 찾을 수 없습니다."}

        fin_result = await db.execute(
            select(Financial)
            .where(Financial.stock_id == stock.id)
            .order_by(Financial.created_at.desc())
            .limit(1)
        )
        fin = fin_result.scalar_one_or_none()

        analysis_result = await db.execute(
            select(Analysis)
            .where(Analysis.stock_id == stock.id, Analysis.period_type == "daily")
            .order_by(Analysis.date.desc())
            .limit(1)
        )
        analysis = analysis_result.scalar_one_or_none()

        recent_summary = None
        recent_keywords = []
        if analysis is not None:
            recent_summary = analysis.summary
            kw_result = await db.execute(
                select(KeywordDetail)
                .where(KeywordDetail.analysis_id == analysis.id)
                .limit(5)
            )
            recent_keywords = [
                {"keyword": k.keyword, "type": k.type, "detail": k.detail}
                for k in kw_result.scalars().all()
            ]

        return {
            "ticker": stock.ticker,
            "name": stock.name,
            "market": stock.market,
            "sector": stock.sector,
            "current_price": stock.current_price,
            "change": stock.change,
            "change_percent": stock.change_percent,
            "per": fin.per if fin else None,
            "pbr": fin.pbr if fin else None,
            "market_cap": fin.market_cap if fin else None,
            "dividend_yield": fin.dividend_yield if fin else None,
            "recent_analysis_summary": recent_summary,
            "recent_analysis_keywords": recent_keywords,
        }


async def get_price_history(ticker: str, days: int = 30) -> dict:
    """최근 N일 일별 OHLC + 핵심 통계.

    시계열 질문 ('한 달 중 가장 떨어진 날', '변동성', '최저/최고가') 전용.
    """
    ticker = ticker.strip().upper()
    days = max(1, min(int(days or 30), 365))
    async with async_session() as db:
        stock_result = await db.execute(
            select(Stock).where(Stock.ticker == ticker)
        )
        stock = stock_result.scalar_one_or_none()
        if not stock:
            return {"error": f"종목 '{ticker}'을(를) 찾을 수 없습니다."}

        since = date.today() - timedelta(days=days)
        ph_result = await db.execute(
            select(PriceHistory)
            .where(PriceHistory.stock_id == stock.id, PriceHistory.date >= since)
            .order_by(PriceHistory.date.asc())
        )
        rows = list(ph_result.scalars().all())
        if not rows:
            return {
                "ticker": stock.ticker,
                "days": days,
                "daily": [],
                "summary": None,
                "note": "DB에 해당 기간 일별 가격이 없습니다.",
            }

        daily = [
            {
                "date": r.date.isoformat() if hasattr(r.date, "isoformat") else str(r.date),
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in rows
        ]

        # 통계: 일별 종가 변화 기반
        max_drop_day = None
        max_drop_pct = 0.0
        max_rise_day = None
        max_rise_pct = 0.0
        for prev, cur in zip(rows[:-1], rows[1:]):
            if prev.close <= 0:
                continue
            pct = (cur.close - prev.close) / prev.close * 100
            if pct < max_drop_pct:
                max_drop_pct = pct
                max_drop_day = cur.date
            if pct > max_rise_pct:
                max_rise_pct = pct
                max_rise_day = cur.date

        first_close = rows[0].close
        last_close = rows[-1].close
        total_change_pct = (
            (last_close - first_close) / first_close * 100 if first_close else 0
        )
        highest = max(rows, key=lambda r: r.high)
        lowest = min(rows, key=lambda r: r.low)

        summary = {
            "first_date": rows[0].date.isoformat(),
            "last_date": rows[-1].date.isoformat(),
            "first_close": first_close,
            "last_close": last_close,
            "total_change_pct": round(total_change_pct, 2),
            "highest_close": highest.close,
            "highest_close_date": highest.date.isoformat(),
            "lowest_close": lowest.close,
            "lowest_close_date": lowest.date.isoformat(),
            "max_drop_day": max_drop_day.isoformat() if max_drop_day else None,
            "max_drop_pct": round(max_drop_pct, 2) if max_drop_day else None,
            "max_rise_day": max_rise_day.isoformat() if max_rise_day else None,
            "max_rise_pct": round(max_rise_pct, 2) if max_rise_day else None,
        }

        return {
            "ticker": stock.ticker,
            "days": days,
            "summary": summary,
            "daily": daily,
        }


async def get_recent_news(ticker: str, days: int = 7) -> list[dict]:
    """최근 N일 뉴스 상위 10건 — 본문 일부(최대 400자) 포함."""
    ticker = ticker.strip().upper()
    async with async_session() as db:
        stock_result = await db.execute(
            select(Stock).where(Stock.ticker == ticker)
        )
        stock = stock_result.scalar_one_or_none()
        if not stock:
            return []

        since = date.today() - timedelta(days=days)
        news_result = await db.execute(
            select(News)
            .where(News.stock_id == stock.id, News.published_at >= since)
            .order_by(News.published_at.desc())
            .limit(10)
        )
        items = []
        for n in news_result.scalars().all():
            content = (n.content or "").strip()
            if len(content) > NEWS_CONTENT_SNIPPET_LEN:
                content = content[:NEWS_CONTENT_SNIPPET_LEN] + "..."
            items.append({
                "title": n.title,
                "published_at": n.published_at.strftime("%Y-%m-%d") if n.published_at else "",
                "source": n.source or "",
                "url": n.url or "",
                "content_snippet": content,
            })
        return items


async def get_recent_disclosures(ticker: str, days: int = 30) -> list[dict]:
    """최근 N일 공시 상위 10건. 시드/수집 안 된 경우 빈 리스트 반환."""
    ticker = ticker.strip().upper()
    days = max(1, min(int(days or 30), 365))
    async with async_session() as db:
        stock_result = await db.execute(
            select(Stock).where(Stock.ticker == ticker)
        )
        stock = stock_result.scalar_one_or_none()
        if not stock:
            return []

        since = date.today() - timedelta(days=days)
        d_result = await db.execute(
            select(Disclosure)
            .where(
                Disclosure.stock_id == stock.id,
                Disclosure.disclosed_at >= since,
            )
            .order_by(Disclosure.disclosed_at.desc())
            .limit(10)
        )
        items = []
        for d in d_result.scalars().all():
            content = (d.content or "").strip()
            if len(content) > DISCLOSURE_CONTENT_SNIPPET_LEN:
                content = content[:DISCLOSURE_CONTENT_SNIPPET_LEN] + "..."
            items.append({
                "title": d.title,
                "disclosure_type": d.disclosure_type,
                "disclosed_at": d.disclosed_at.strftime("%Y-%m-%d") if d.disclosed_at else "",
                "content_snippet": content,
            })
        return items


async def get_exchange_rate(pair: str = "USD/KRW") -> dict:
    """가장 최신 환율 1개. pair 예: 'USD/KRW', 'EUR/KRW'."""
    pair = (pair or "USD/KRW").strip().upper()
    async with async_session() as db:
        r_result = await db.execute(
            select(ExchangeRate)
            .where(ExchangeRate.currency_pair == pair)
            .order_by(desc(ExchangeRate.date))
            .limit(1)
        )
        row = r_result.scalar_one_or_none()
        if not row:
            return {"error": f"환율 '{pair}' DB에 없음 (수집 안 됐을 수 있음)."}
        return {
            "pair": row.currency_pair,
            "rate": row.rate,
            "date": row.date.isoformat(),
        }


async def search_stocks(query: str) -> list[dict]:
    """종목 이름 또는 ticker로 DB 검색 (최대 5건)."""
    query = (query or "").strip()
    if not query:
        return []
    async with async_session() as db:
        stmt = (
            select(Stock)
            .where(Stock.name.ilike(f"%{query}%") | Stock.ticker.ilike(f"%{query}%"))
            .limit(5)
        )
        result = await db.execute(stmt)
        return [
            {"ticker": s.ticker, "name": s.name, "market": s.market, "sector": s.sector}
            for s in result.scalars().all()
        ]


async def list_stocks_by_sector(sector: str) -> list[dict]:
    """sector 컬럼 substring 매칭으로 종목 나열 (최대 20건).

    답변 시 반드시 이 결과만 사용 — DB에 없는 종목 추측 금지.
    """
    sector = (sector or "").strip()
    if not sector:
        return []
    async with async_session() as db:
        stmt = (
            select(Stock)
            .where(Stock.sector.ilike(f"%{sector}%"))
            .limit(20)
        )
        result = await db.execute(stmt)
        items = [
            {
                "ticker": s.ticker,
                "name": s.name,
                "market": s.market,
                "sector": s.sector,
            }
            for s in result.scalars().all()
        ]
        if not items:
            return []
        return items


async def get_my_favorites(user_id: str) -> list[dict]:
    """현재 로그인 사용자의 즐겨찾기 종목 + 현재가/등락.

    user_id는 orchestrator가 인증 컨텍스트에서 주입 — LLM이 임의로 못 바꾼다.
    """
    if not user_id:
        return []
    async with async_session() as db:
        stmt = (
            select(Stock)
            .join(Favorite, Favorite.stock_id == Stock.id)
            .where(Favorite.user_id == user_id)
        )
        result = await db.execute(stmt)
        return [
            {
                "ticker": s.ticker,
                "name": s.name,
                "market": s.market,
                "sector": s.sector,
                "current_price": s.current_price,
                "change_percent": s.change_percent,
            }
            for s in result.scalars().all()
        ]


# --- Tool schemas for Foundry Responses API ---

TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "get_stock_snapshot",
        "description": (
            "종목의 기본 정보, **현재가(단일 시점)**, 최신 분석 요약, 최신 재무지표(PER/PBR/시총/배당)를 조회. "
            "**시계열·기간별 추이가 필요하면 이 도구가 아니라 get_price_history를 써라.**"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "종목 코드 (예: '005930', 'TSLA')"},
            },
            "required": ["ticker"],
        },
    },
    {
        "type": "function",
        "name": "get_price_history",
        "description": (
            "최근 N일 일별 OHLC + 통계(최대낙폭일, 최대상승일, 기간 최고/최저가, 누적 수익률). "
            "**'한 달 중 가장 많이 떨어진 날', '변동성', '최저/최고가', '추세'** 등 시계열·기간성 질문에 반드시 이 도구를 써라."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "days": {"type": "integer", "description": "최근 며칠 (기본 30, 최대 365)", "default": 30},
            },
            "required": ["ticker"],
        },
    },
    {
        "type": "function",
        "name": "get_recent_news",
        "description": "종목의 최근 뉴스 (제목, 출처, URL, 본문 일부). '뉴스/소식/기사/본문 요약' 류 질문에 사용.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "days": {"type": "integer", "description": "최근 며칠 (기본 7)", "default": 7},
            },
            "required": ["ticker"],
        },
    },
    {
        "type": "function",
        "name": "get_recent_disclosures",
        "description": "종목 공시 (DART/SEC). '공시/disclosure/공시 알려줘' 류 질문에 사용.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "days": {"type": "integer", "description": "최근 며칠 (기본 30)", "default": 30},
            },
            "required": ["ticker"],
        },
    },
    {
        "type": "function",
        "name": "get_exchange_rate",
        "description": "가장 최신 환율 1건. pair 예: 'USD/KRW' (원/달러), 'EUR/KRW'.",
        "parameters": {
            "type": "object",
            "properties": {
                "pair": {"type": "string", "description": "환율 쌍 (기본 USD/KRW)", "default": "USD/KRW"},
            },
        },
    },
    {
        "type": "function",
        "name": "search_stocks",
        "description": "종목 이름 또는 ticker로 검색. 사용자가 종목명만 말했을 때 ticker 확보용.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "종목명 또는 ticker"},
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "list_stocks_by_sector",
        "description": (
            "sector 필드 매칭으로 DB에 등록된 종목 나열. '반도체 섹터 종목', '기술주 뭐있어' 류 질문에 사용. "
            "**결과가 비어 있으면 '등록된 종목이 없다'고 답할 것 — DB에 없는 종목명을 추측해서 나열하면 안 된다.**"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sector": {"type": "string", "description": "예: '반도체', 'Technology', 'Consumer'"},
            },
            "required": ["sector"],
        },
    },
    {
        "type": "function",
        "name": "get_my_favorites",
        "description": (
            "현재 로그인한 사용자의 즐겨찾기 종목 + 현재가/등락률. "
            "'내 즐겨찾기', '내 종목', '내가 찜한' 류 질문에 사용. "
            "user_id는 시스템이 자동 주입하므로 인자로 받지 않는다."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
]

TOOL_FUNCTIONS = {
    "get_stock_snapshot": get_stock_snapshot,
    "get_price_history": get_price_history,
    "get_recent_news": get_recent_news,
    "get_recent_disclosures": get_recent_disclosures,
    "get_exchange_rate": get_exchange_rate,
    "search_stocks": search_stocks,
    "list_stocks_by_sector": list_stocks_by_sector,
    "get_my_favorites": get_my_favorites,
}

# Tools that need user_id from the orchestrator (never from the LLM).
USER_SCOPED_TOOLS = {"get_my_favorites"}
