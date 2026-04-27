import asyncio
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.collectors.scraper import scrape_news_content
from app.models import Stock
from app.models.news import News

logger = logging.getLogger(__name__)


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

        content = strip_html(item.get("description", "")) or None

        stmt = insert(News).values(
            stock_id=stock.id,
            title=strip_html(item.get("title", "")),
            source="네이버뉴스",
            url=item.get("link", ""),
            published_at=pub_date,
            content=content,
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


# --- NewsAPI (US 보조) ---


async def fetch_newsapi(query: str, page_size: int = 30) -> dict:  # pragma: no cover
    """NewsAPI.org에서 뉴스를 검색한다.

    `qInTitle`을 쓰면 본문에 종목명이 우연히 한 번 등장하는 광범위 매칭
    (예: 'Laptop very slow' 같은 무관 기사가 'Microsoft' 한 단어로 끌려오는 케이스)
    을 차단한다. 제목에 종목명/티커가 들어간 기사만 통과.
    """
    url = "https://newsapi.org/v2/everything"
    params = {
        "qInTitle": query,
        "pageSize": page_size,
        "sortBy": "publishedAt",
        "language": "en",
        "apiKey": settings.newsapi_key,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def _build_newsapi_query(stock: Stock) -> str:
    """제목 매칭용 쿼리: '"<풀네임>" OR <티커>'.

    풀네임은 따옴표로 감싸 정확 일치를 노리고, 티커는 단독 토큰으로 매칭.
    예: '"Microsoft Corporation" OR MSFT'.
    """
    name = (stock.name or "").strip()
    ticker = (stock.ticker or "").strip()
    if name and ticker:
        return f'"{name}" OR {ticker}'
    return name or ticker


async def _sync_newsapi(db: AsyncSession, stock: Stock) -> dict:
    """NewsAPI.org로 US 종목 뉴스를 보조 수집한다."""
    if not settings.newsapi_key:
        return {"news_synced": 0}

    try:
        data = await fetch_newsapi(_build_newsapi_query(stock))
    except Exception as e:
        return {"news_synced": 0, "error": f"NewsAPI 조회 실패: {e}"}

    articles = data.get("articles", [])
    count = 0
    for article in articles:
        title = article.get("title", "")
        url = article.get("url", "")
        source_name = article.get("source", {}).get("name", "NewsAPI")

        pub_str = article.get("publishedAt", "")
        try:
            pub_date = datetime.fromisoformat(pub_str.replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, TypeError):
            pub_date = datetime.now(timezone.utc).replace(tzinfo=None)

        if not title or not url or title == "[Removed]":
            continue

        content = article.get("description") or article.get("content") or None

        stmt = insert(News).values(
            stock_id=stock.id,
            title=title[:500],
            source=source_name,
            url=url[:1000],
            published_at=pub_date,
            content=content,
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
        yf_result = await _sync_yfinance_news(db, stock)
        api_result = await _sync_newsapi(db, stock)
        total = yf_result.get("news_synced", 0) + api_result.get("news_synced", 0)
        errors = []
        for r in [yf_result, api_result]:
            if "error" in r:
                errors.append(r["error"])
        result = {"news_synced": total}
        if errors:
            result["error"] = "; ".join(errors)
    else:
        result = await _sync_naver_news(db, stock)

    # 본문 스크래핑 (실패해도 뉴스 수집 결과는 유지)
    try:
        scrape_result = await scrape_news_content(db, stock.id)
        result["scraped"] = scrape_result.get("scraped", 0)
    except Exception as e:
        logger.warning("Content scraping failed for %s: %s", stock.ticker, e)
        result["scraped"] = 0

    return result
