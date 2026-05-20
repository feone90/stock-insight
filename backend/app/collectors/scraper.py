"""뉴스 기사 본문 스크래핑."""

import asyncio
import json
import logging
import re
from urllib.parse import urljoin, urlparse

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
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

DOMAIN_SELECTORS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("n.news.naver.com", ("#dic_area", "#newsct_article")),
    ("news.naver.com", ("#dic_area", "#newsct_article")),
    ("finance.yahoo.com", ("[data-testid='article-body']", ".caas-body", ".article-content", "article")),
    ("fool.com", ("[data-test-id='article-body']", ".article-body", "article")),
    ("thestreet.com", (".m-detail--body", ".article-body", ".article-content", "article")),
)
GENERIC_SELECTORS = (
    "article",
    ".article-body",
    ".article-content",
    ".entry-content",
    "[itemprop='articleBody']",
    "main",
)


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


def _extract_text(html: str, url: str = "") -> str | None:  # pragma: no cover
    """Extract article body with site selectors first, then generic engines."""
    selector_text = _extract_text_with_selectors(html, url)
    if selector_text:
        return selector_text[:MAX_CONTENT_LENGTH]

    jsonld_text = _extract_article_body_from_jsonld(html)
    if jsonld_text:
        return jsonld_text[:MAX_CONTENT_LENGTH]

    import trafilatura

    text = trafilatura.extract(html, include_comments=False, include_tables=False)
    return _clean_extracted_text(text) if text else None


async def fetch_article_content(url: str) -> str | None:
    """URL에서 기사 본문을 스크래핑한다."""
    html = await _fetch_html(url)
    if not html:
        return None
    text = await asyncio.to_thread(_extract_text, html, url)
    if text:
        return text[:MAX_CONTENT_LENGTH]

    content_url = url
    redirect_url = _extract_script_redirect_url(html, url)
    if redirect_url:
        redirected_html = await _fetch_html(redirect_url)
        if redirected_html:
            html = redirected_html
            content_url = redirect_url

    text = await asyncio.to_thread(_extract_text, html, content_url)
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


def _extract_text_with_selectors(html: str, url: str = "") -> str | None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    selectors = list(_selectors_for_url(url)) + list(GENERIC_SELECTORS)
    seen: set[str] = set()
    for selector in selectors:
        if selector in seen:
            continue
        seen.add(selector)
        node = soup.select_one(selector)
        if not node:
            continue
        text = _clean_extracted_text(node.get_text("\n", strip=True))
        if text and len(text) >= MIN_CONTENT_LENGTH:
            return text
    return None


def _selectors_for_url(url: str) -> tuple[str, ...]:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    matched: list[str] = []
    for domain, selectors in DOMAIN_SELECTORS:
        if host == domain or host.endswith("." + domain):
            matched.extend(selectors)
    return tuple(matched)


def _extract_article_body_from_jsonld(html: str) -> str | None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        body = _find_jsonld_article_body(parsed)
        text = _clean_extracted_text(body)
        if text and len(text) >= MIN_CONTENT_LENGTH:
            return text
    return None


def _find_jsonld_article_body(value: object) -> str | None:
    if isinstance(value, dict):
        body = value.get("articleBody")
        if isinstance(body, str) and body.strip():
            return body
        graph = value.get("@graph")
        if graph:
            found = _find_jsonld_article_body(graph)
            if found:
                return found
        for child in value.values():
            found = _find_jsonld_article_body(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_jsonld_article_body(child)
            if found:
                return found
    return None


def _clean_extracted_text(text: str | None) -> str | None:
    if not text:
        return None
    lines = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if line in {"ADVERTISEMENT", "Advertisement", "광고"}:
            continue
        lines.append(line)
    cleaned = "\n".join(lines).strip()
    return cleaned or None


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
