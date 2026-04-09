import re
from datetime import datetime
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


async def fetch_naver_news(query: str, display: int = 50) -> dict:
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


async def sync_news(db: AsyncSession, stock: Stock) -> dict:
    """종목 관련 뉴스를 동기화한다."""
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
            # Convert to naive UTC for TIMESTAMP WITHOUT TIME ZONE column
            if pub_date.tzinfo is not None:
                from datetime import timezone
                pub_date = pub_date.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            from datetime import timezone
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
