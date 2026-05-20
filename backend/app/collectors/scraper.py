"""뉴스 기사 본문 스크래핑."""

import asyncio
import logging
import re
from urllib.parse import urljoin

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import News

logger = logging.getLogger(__name__)

SCRAPE_TIMEOUT = 10
MAX_CONTENT_LENGTH = 5000
SCRAPE_CONCURRENCY = 5
MIN_CONTENT_LENGTH = 200

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


async def _fetch_html(url: str) -> str | None:  # pragma: no cover
    """URL에서 HTML을 가져온다."""
    try:
        async with httpx.AsyncClient(
            timeout=SCRAPE_TIMEOUT, follow_redirects=True, headers=HEADERS
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            return resp.text
    except Exception:
        return None


def _extract_text(html: str) -> str | None:  # pragma: no cover
    """trafilatura로 HTML에서 기사 본문을 추출한다."""
    import trafilatura

    return trafilatura.extract(html, include_comments=False, include_tables=False)


async def fetch_article_content(url: str) -> str | None:
    """URL에서 기사 본문을 스크래핑한다."""
    html = await _fetch_html(url)
    if not html:
        return None
    redirect_url = _extract_script_redirect_url(html, url)
    if redirect_url:
        redirected_html = await _fetch_html(redirect_url)
        if redirected_html:
            html = redirected_html

    text = await asyncio.to_thread(_extract_text, html)
    if text:
        return text[:MAX_CONTENT_LENGTH]
    return None


def _extract_script_redirect_url(html: str, base_url: str) -> str | None:
    """Handle finance.naver.com article pages that return a JS redirect only."""
    match = re.search(
        r"(?:(?:top|window)\.)?location(?:\.href)?\s*=\s*['\"]([^'\"]+)['\"]",
        html,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return urljoin(base_url, match.group(1))


async def scrape_news_content(
    db: AsyncSession,
    stock_id: int,
    limit: int = 40,
) -> dict:
    """본문이 없거나 짧은 기사의 content를 스크래핑으로 채운다.

    Returns:
        {"scraped": N} — 실제로 content가 업데이트된 기사 수
    """
    result = await db.execute(
        select(News)
        .where(
            News.stock_id == stock_id,
            (News.content.is_(None))
            | (func.length(News.content) < MIN_CONTENT_LENGTH),
        )
        .order_by(News.published_at.desc())
        .limit(limit)
    )
    articles = result.scalars().all()

    if not articles:
        return {"scraped": 0}

    sem = asyncio.Semaphore(SCRAPE_CONCURRENCY)

    async def _scrape_one(article: News) -> bool:
        async with sem:
            content = await fetch_article_content(article.url)
            if content and len(content) > len(article.content or ""):
                article.content = content
                return True
            return False

    tasks = [_scrape_one(a) for a in articles if a.url]
    results = await asyncio.gather(*tasks)

    count = sum(1 for r in results if r)
    if count > 0:
        await db.commit()

    return {"scraped": count}
