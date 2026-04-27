"""LLM chat agent tools — DB access functions.

Each tool opens its own async_session (same pattern as scheduler._sync_single_stock).
Returns dict on success, {"error": "..."} on known error. Never raises for expected errors.
"""

import logging
from datetime import date, timedelta

from sqlalchemy import select

from app.database import async_session
from app.models import Stock, Financial, PriceHistory
from app.models.analysis import Analysis, KeywordDetail
from app.models.news import News

logger = logging.getLogger(__name__)


async def get_stock_snapshot(ticker: str) -> dict:
    """종목 기본정보 + 최근 가격 + 최신 분석 + 재무지표 통합 조회."""
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


async def get_recent_news(ticker: str, days: int = 7) -> list[dict]:
    """최근 N일 뉴스 상위 10건."""
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
        return [
            {
                "title": n.title,
                "published_at": n.published_at.strftime("%Y-%m-%d") if n.published_at else "",
                "source": n.source or "",
                "url": n.url or "",
            }
            for n in news_result.scalars().all()
        ]


async def search_stocks(query: str) -> list[dict]:
    """종목 이름 또는 ticker로 DB 검색 (최대 5건)."""
    query = query.strip()
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
            {"ticker": s.ticker, "name": s.name, "market": s.market}
            for s in result.scalars().all()
        ]


# --- Tool schemas for Foundry Responses API ---

TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "get_stock_snapshot",
        "description": "종목의 기본 정보, 현재가, 최신 분석 요약, 재무지표를 한 번에 조회. 종목에 대한 일반적 질문에 먼저 사용.",
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
        "name": "get_recent_news",
        "description": "종목의 최근 뉴스를 조회. 사용자가 '뉴스', '소식'을 명시적으로 물을 때 사용.",
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
        "name": "search_stocks",
        "description": "종목 이름이나 ticker로 검색. 사용자가 종목명만 말했을 때 ticker 확보용.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "종목명 또는 ticker (예: '삼성', 'TSLA')"},
            },
            "required": ["query"],
        },
    },
]

TOOL_FUNCTIONS = {
    "get_stock_snapshot": get_stock_snapshot,
    "get_recent_news": get_recent_news,
    "search_stocks": search_stocks,
}
