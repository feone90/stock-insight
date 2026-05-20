import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.publisher_whitelist import is_trusted_kr, is_trusted_us
from app.collectors.scraper import scrape_news_content
from app.config import settings
from app.markets import is_us
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
    skipped = 0
    for item in items:
        url = item.get("link", "")
        # Codex 권고 (2026-05-14): Naver 결과는 publisher whitelist 통과한 것만
        # DB insert. 블로그·SEO 스팸·aggregator·티스토리·네이버블로그 자동 drop.
        if not is_trusted_kr(url):
            skipped += 1
            continue
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
            url=url,
            published_at=pub_date,
            content=content,
        ).on_conflict_do_nothing(constraint="uq_news_stock_url")
        result = await db.execute(stmt)
        if result.rowcount > 0:
            count += 1

    await db.commit()
    if skipped:
        logger.info("naver news whitelist filter: kept=%d skipped=%d", count, skipped)
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
    skipped = 0
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
        if not is_trusted_us(url):
            skipped += 1
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
    if skipped:
        logger.info("yfinance news whitelist filter: kept=%d skipped=%d", count, skipped)
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
    skipped = 0
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
        if not is_trusted_us(url):
            skipped += 1
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
    if skipped:
        logger.info("newsapi whitelist filter: kept=%d skipped=%d", count, skipped)
    return {"news_synced": count}


# --- Google News (KR 보조) ---


_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
_GOOGLE_NEWS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml,text/xml,*/*",
}


async def _fetch_google_news_kr(query: str) -> str | None:  # pragma: no cover
    """Google News 한국 RSS — 회사명 검색으로 직접 매칭되는 기사 수집.

    Naver Open API 와 달리 매일경제 / 한국경제 / 머니투데이 / 이데일리 / 연합뉴스
    등 증권 전문 매체 + 영문 매체까지 한 번에 잡힘. description 본문은 짧지만
    URL 은 정상 매체 직접 링크라 trafilatura 스크래핑이 잘 통한다.
    """
    params = {"q": query, "hl": "ko-KR", "gl": "KR", "ceid": "KR:ko"}
    # Google News 는 hl/gl 정규화로 항상 301 redirect — follow_redirects 필수.
    async with httpx.AsyncClient(
        timeout=30, headers=_GOOGLE_NEWS_HEADERS, follow_redirects=True
    ) as client:
        resp = await client.get(_GOOGLE_NEWS_RSS, params=params)
        if resp.status_code != 200:
            return None
        return resp.text


def _parse_google_news_items(xml_text: str) -> list[dict]:
    """RSS 2.0 → list of dicts. <description> 안의 source/링크 HTML 은 분리."""
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    channel = root.find("channel")
    if channel is None:
        return items
    for item in channel.findall("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pub_el = item.find("pubDate")
        src_el = item.find("source")
        desc_el = item.find("description")
        if title_el is None or link_el is None:
            continue
        title = strip_html(title_el.text or "").strip()
        url = (link_el.text or "").strip()
        if not title or not url:
            continue
        source_name = (src_el.text or "Google News").strip() if src_el is not None else "Google News"
        pub_date = None
        if pub_el is not None and pub_el.text:
            try:
                pd = parsedate_to_datetime(pub_el.text)
                pub_date = pd.astimezone(timezone.utc).replace(tzinfo=None) if pd.tzinfo else pd
            except Exception:
                pub_date = None
        description = strip_html(desc_el.text or "").strip() if desc_el is not None else ""
        items.append(
            {
                "title": title,
                "url": url,
                "source": source_name,
                "published_at": pub_date or datetime.now(timezone.utc).replace(tzinfo=None),
                "description": description or None,
            }
        )
    return items


async def _sync_google_news_kr(db: AsyncSession, stock: Stock) -> dict:
    """Google News RSS 로 KR 종목 뉴스 보조 수집."""
    query = (stock.name or "").strip() or stock.ticker
    try:
        xml_text = await _fetch_google_news_kr(query)
    except Exception as e:
        return {"news_synced": 0, "error": f"Google News 조회 실패: {e}"}
    if not xml_text:
        return {"news_synced": 0, "error": "Google News empty response"}

    count = 0
    skipped = 0
    for item in _parse_google_news_items(xml_text):
        # Google News RSS는 매체 직접 link → publisher whitelist 적용.
        # 단 news.google.com 자체 redirect URL은 whitelist에 포함시켜 통과.
        if not is_trusted_kr(item["url"]):
            skipped += 1
            continue
        stmt = insert(News).values(
            stock_id=stock.id,
            title=item["title"][:500],
            source=item["source"][:100],
            url=item["url"][:1000],
            published_at=item["published_at"],
            content=item.get("description"),
        ).on_conflict_do_nothing(constraint="uq_news_stock_url")
        result = await db.execute(stmt)
        if result.rowcount > 0:
            count += 1
    await db.commit()
    if skipped:
        logger.info("google news kr whitelist filter: kept=%d skipped=%d", count, skipped)
    return {"news_synced": count}


# --- Naver Finance (KR primary — entity matching 이미 정확) ---


_NAVER_FINANCE_NEWS_URL = "https://finance.naver.com/item/news_news.naver"
_NAVER_FINANCE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    ),
}


async def _fetch_naver_finance_news_pages(  # pragma: no cover
    ticker: str, pages: int = 4
) -> str | None:
    """네이버 증권 종목별 뉴스 list page fetch.

    URL: finance.naver.com/item/news_news.naver?code=NNNNNN&page=N
    page=1 헤더에 Referer (news.naver.com) 안 박으면 빈 응답 가능. EUC-KR
    인코딩.

    2026-05-14 사용자 제안 — Open Search API 는 키워드 검색이라 entity
    ambiguity (회사명 우연 일치 기사) 있고, finance.naver.com 종목별 페이지는
    네이버가 이미 직접 큐레이션해서 entity matching 정확. KR-only.
    """
    headers = {
        **_NAVER_FINANCE_HEADERS,
        "Referer": f"https://finance.naver.com/item/news.naver?code={ticker}",
    }
    chunks: list[str] = []
    async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as client:
        for page in range(1, pages + 1):
            params = {
                "code": ticker,
                "page": str(page),
                "sm": "title_entity_id.basic",
                "clusterId": "",
            }
            try:
                resp = await client.get(_NAVER_FINANCE_NEWS_URL, params=params)
                resp.raise_for_status()
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "naver finance news fetch fail %s p%d: %s", ticker, page, e
                )
                continue
            chunks.append(resp.content.decode("euc-kr", errors="replace"))
    return "\n".join(chunks) if chunks else None


def _parse_naver_finance_news(html: str) -> list[dict]:
    """table tr → (title, source, date, url) — bs4 파싱."""
    from bs4 import BeautifulSoup

    items: list[dict] = []
    soup = BeautifulSoup(html, "html.parser")
    for tr in soup.select("tr"):
        link = tr.select_one("td a[href*='/item/news_read.naver']")
        info = tr.select_one("td.info")
        date_td = tr.select_one("td.date")
        if not link or not info or not date_td:
            continue
        title = (link.get_text() or "").strip()
        href = link.get("href") or ""
        source = (info.get_text() or "").strip()
        date_str = (date_td.get_text() or "").strip()
        if not title or not href:
            continue
        url = (
            f"https://finance.naver.com{href}"
            if href.startswith("/")
            else href
        )
        published_at: datetime | None = None
        for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
            try:
                published_at = datetime.strptime(date_str, fmt)
                break
            except ValueError:
                continue
        if published_at is None:
            published_at = datetime.now(timezone.utc).replace(tzinfo=None)
        items.append(
            {
                "title": title,
                "source": source or "네이버증권",
                "url": url,
                "published_at": published_at,
            }
        )
    return items


async def _sync_naver_finance_news(db: AsyncSession, stock: Stock) -> dict:
    """네이버 증권 종목별 뉴스 동기화 — KR-only.

    Open Search API 보다 정확한 entity matching (네이버가 직접 큐레이션).
    매체는 publisher whitelist 통과한 것만 keep — finance.naver.com host 가
    KR_TRUSTED 포함되어 redirect URL 도 자연스럽게 통과.
    """
    try:
        html = await _fetch_naver_finance_news_pages(stock.ticker)
    except Exception as e:  # noqa: BLE001
        return {"news_synced": 0, "error": f"네이버 증권 fetch 실패: {e}"}
    if not html:
        return {"news_synced": 0, "error": "네이버 증권 빈 응답"}

    items = _parse_naver_finance_news(html)
    if not items:
        return {"news_synced": 0}

    count = 0
    skipped = 0
    for item in items:
        url = item["url"]
        if not is_trusted_kr(url):
            skipped += 1
            continue
        stmt = insert(News).values(
            stock_id=stock.id,
            title=item["title"][:500],
            source=item["source"][:100],
            url=url[:1000],
            published_at=item["published_at"],
        ).on_conflict_do_nothing(constraint="uq_news_stock_url")
        result = await db.execute(stmt)
        if result.rowcount > 0:
            count += 1

    await db.commit()
    if skipped:
        logger.info(
            "naver finance whitelist filter: kept=%d skipped=%d", count, skipped
        )
    return {"news_synced": count}


# --- 통합 ---


async def sync_news(db: AsyncSession, stock: Stock) -> dict:
    """종목 시장에 따라 적절한 뉴스 소스로 동기화한다.

    KR: Naver Open API + Google News RSS (보조 — 증권 전문매체 + 외신).
    US: yfinance + NewsAPI.
    """
    if is_us(stock.market):
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
        # 2026-05-14 — 네이버 증권 종목별 페이지 primary (entity matching 정확).
        # Open Search API + Google News RSS 는 보완 (드물게 증권 페이지가
        # 놓친 매체 잡힘). 다 union, URL unique constraint 가 dedup.
        naver_finance = await _sync_naver_finance_news(db, stock)
        naver_result = await _sync_naver_news(db, stock)
        gnews_result = await _sync_google_news_kr(db, stock)
        total = (
            naver_finance.get("news_synced", 0)
            + naver_result.get("news_synced", 0)
            + gnews_result.get("news_synced", 0)
        )
        errors = []
        for r in [naver_finance, naver_result, gnews_result]:
            if "error" in r:
                errors.append(r["error"])
        result = {"news_synced": total}
        if errors:
            result["error"] = "; ".join(errors)

    # 본문 스크래핑 (실패해도 뉴스 수집 결과는 유지)
    try:
        scrape_result = await scrape_news_content(db, stock.id)
        result["scraped"] = scrape_result.get("scraped", 0)
    except Exception as e:
        logger.warning("Content scraping failed for %s: %s", stock.ticker, e)
        result["scraped"] = 0

    return result
