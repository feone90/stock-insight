"""정치 발언 crawler — trumpstruth.org RSS feed.

이전 시도 fail:
  - truthsocial.com API: 403 (Cloudflare 차단)
  - nitter (X mirror): instances 다 down

현재: trumpstruth.org — Truth Social 게시물을 추적/아카이브하는 3rd party.
정상 RSS 2.0 feed 제공 + 인증 불필요 + fresh (실시간 mirror).

DB source value: "trumpstruth_org". source_post_id는 link URL의 statuses/{id}.
"""
from __future__ import annotations

import html as html_lib
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.political_signal import PoliticalSignal

logger = logging.getLogger(__name__)

TRUMPSTRUTH_RSS_URL = "https://trumpstruth.org/feed"
TRUMPSTRUTH_USER = "realDonaldTrump"
SOURCE_LABEL = "trumpstruth_org"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml,text/xml,*/*",
}


async def sync_truth_social(db: AsyncSession, limit: int = 20) -> dict:
    """trumpstruth.org RSS feed에서 fetch + dedup INSERT.

    Returns:
        {"fetched": int, "inserted": int, "skipped": int, "error": str?}
    """
    try:
        async with httpx.AsyncClient(
            timeout=15.0, headers=HEADERS, follow_redirects=True
        ) as client:
            resp = await client.get(TRUMPSTRUTH_RSS_URL)
            resp.raise_for_status()
            rss_text = resp.text
    except Exception as e:  # noqa: BLE001
        logger.warning("trumpstruth fetch failed: %s", e)
        return {
            "fetched": 0,
            "inserted": 0,
            "skipped": 0,
            "error": f"fetch failed: {e}",
        }

    items = _parse_rss(rss_text)
    if not items:
        return {
            "fetched": 0,
            "inserted": 0,
            "skipped": 0,
            "error": "RSS parse 결과 0건",
        }

    inserted = 0
    skipped = 0
    for item in items[:limit]:
        post_id = item.get("id")
        content = item.get("content") or ""
        if not post_id or not content.strip():
            skipped += 1
            continue
        stmt = (
            pg_insert(PoliticalSignal)
            .values(
                source=SOURCE_LABEL,
                source_post_id=str(post_id)[:128],
                author=TRUMPSTRUTH_USER,
                posted_at=item["posted_at"],
                content=content[:4000],
                content_lang="en",
                url=item.get("url"),
            )
            .on_conflict_do_nothing(
                index_elements=["source", "source_post_id"],
            )
        )
        result = await db.execute(stmt)
        if result.rowcount and result.rowcount > 0:
            inserted += 1
        else:
            skipped += 1

    await db.commit()
    logger.info(
        "trumpstruth sync: fetched=%d inserted=%d skipped=%d",
        len(items),
        inserted,
        skipped,
    )
    return {
        "fetched": len(items),
        "inserted": inserted,
        "skipped": skipped,
    }


def _parse_rss(rss_text: str) -> list[dict]:
    """Standard RSS 2.0 channel/item 파싱."""
    out: list[dict] = []
    try:
        root = ET.fromstring(rss_text)
    except ET.ParseError as e:
        logger.warning("rss parse fail: %s", e)
        return out
    channel = root.find("channel")
    if channel is None:
        return out
    for item in channel.findall("item"):
        guid = (item.findtext("guid") or "").strip()
        link = (item.findtext("link") or "").strip()
        content_html = item.findtext("description") or ""
        content = _strip_html(content_html)
        pub_date_str = item.findtext("pubDate") or ""
        try:
            posted_at = parsedate_to_datetime(pub_date_str).replace(tzinfo=None)
        except Exception:
            posted_at = datetime.utcnow()
        out.append(
            {
                "id": guid or link,
                "content": content,
                "posted_at": posted_at,
                "url": link or None,
            }
        )
    return out


def _strip_html(html: str) -> str:
    """RSS description의 minimal HTML → plain text."""
    s = re.sub(r"<br\s*/?>", "\n", html)
    s = re.sub(r"</p>\s*<p>", "\n\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return html_lib.unescape(s).strip()
