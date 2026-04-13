import asyncio
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Stock
from app.models.news import News


def strip_html(text: str) -> str:
    """HTML 태그 제거."""
    return re.sub(r"<[^>]+>", "", text)


# --- Naver (KR) ---


async def fetch_naver_news(query: str, display: int = 50) -> dict:  # pragma: no cover
    """Naver News API 호출."""
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": settings.naver_client_id,
        "X-Naver-Client-Secret": settings.naver_client_secret,
    }
    params = {"query": query, "display": display, "sort": "date"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()


async def _sync_naver_news(db: AsyncSession, stock: Stock) -> dict:
    """Naver News API로 한국 종목 뉴스를 동기화한다."""
    if not settings.naver_client_id or not settings.naver_client_secret:
        return {"news_synced": 0, "error": "Naver API 키 미설정"}

    try:
        data = await fetch_naver_news(stock.name)
    except Exception as e:
        return {"news_synced": 0, "error": f"뉴스 조회 실패: {e}"}

    items = data.get("items", [])
    count = 0
    for item in items:
        try:
            pub_date = parsedate_to_datetime(item["pubDate"])
            if pub_date.tzinfo is not None:
                pub_date = pub_date.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            pub_date = datetime.now(timezone.utc).replace(tzinfo=None)

        stmt = insert(News).values(
            stock_id=stock.id,
            title=strip_html(item.get("title", "")),
            source="네이버뉴스",
            url=item.get("link", ""),
            published_at=pub_date,
        ).on_conflict_do_nothing(constraint="uq_news_stock_url")
        result = await db.execute(stmt)
        if result.rowcount > 0:
            count += 1

    await db.commit()
    return {"news_synced": count}


# --- yfinance (US) ---


def _fetch_yfinance_news(ticker: str) -> list[dict]:  # pragma: no cover
    """yfinance로 US 종목 뉴스를 가져온다 (동기 호출)."""
    import yfinance as yf
    t = yf.Ticker(ticker)
    return t.news or []


async def _sync_yfinance_news(db: AsyncSession, stock: Stock) -> dict:
    """yfinance로 미국 종목 뉴스를 동기화한다."""
    try:
        articles = await asyncio.to_thread(_fetch_yfinance_news, stock.ticker)
    except Exception as e:
        return {"news_synced": 0, "error": f"US 뉴스 조회 실패: {e}"}

    count = 0
    for article in articles:
        # 새 형식: {"id", "content": {...}} / 구 형식: {"title", "link", ...}
        content = article.get("content", article)

        title = content.get("title", "")
        # URL: canonicalUrl.url > clickThroughUrl.url > link > url
        url = ""
        for url_field in ("canonicalUrl", "clickThroughUrl"):
            url_obj = content.get(url_field)
            if isinstance(url_obj, dict) and url_obj.get("url"):
                url = url_obj["url"]
                break
        if not url:
            url = content.get("link", "") or content.get("url", "")

        # Publisher
        provider = content.get("provider")
        publisher = provider.get("displayName", "Yahoo Finance") if isinstance(provider, dict) else content.get("publisher", "Yahoo Finance")

        # Date: pubDate (ISO string) > providerPublishTime (timestamp)
        pub_date_str = content.get("pubDate")
        pub_ts = content.get("providerPublishTime")
        if pub_date_str and isinstance(pub_date_str, str):
            try:
                from datetime import datetime as dt_cls
                pub_date = dt_cls.fromisoformat(pub_date_str.replace("Z", "+00:00")).replace(tzinfo=None)
            except (ValueError, TypeError):
                pub_date = datetime.now(timezone.utc).replace(tzinfo=None)
        elif pub_ts and isinstance(pub_ts, (int, float)):
            pub_date = datetime.fromtimestamp(pub_ts, tz=timezone.utc).replace(tzinfo=None)
        else:
            pub_date = datetime.now(timezone.utc).replace(tzinfo=None)

        if not title or not url:
            continue

        stmt = insert(News).values(
            stock_id=stock.id,
            title=title[:500],
            source=publisher,
            url=url[:1000],
            published_at=pub_date,
        ).on_conflict_do_nothing(constraint="uq_news_stock_url")
        result = await db.execute(stmt)
        if result.rowcount > 0:
            count += 1

    await db.commit()
    return {"news_synced": count}


# --- 통합 ---


async def sync_news(db: AsyncSession, stock: Stock) -> dict:
    """종목 시장에 따라 적절한 뉴스 소스로 동기화한다."""
    if stock.market in ("NYSE", "NASDAQ"):
        return await _sync_yfinance_news(db, stock)
    return await _sync_naver_news(db, stock)
