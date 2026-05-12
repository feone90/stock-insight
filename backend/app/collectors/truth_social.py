"""정치 발언 crawler — 트럼프 X (Twitter) via nitter mirror.

Truth Social 직접 API는 403 Forbidden (Cloudflare). X (Twitter)가 더
활성 + nitter는 anonymous RSS mirror라 인증 불필요.

nitter instances는 자주 down → fallback chain (4개 instance). 첫 200 OK +
valid RSS 응답 사용.

DB source value는 "x_trump_nitter" (truth_social.py 파일 이름은 호환성
유지 — admin job_id "truth_social"도 그대로).
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

NITTER_USER = "realDonaldTrump"

# Fallback chain — public nitter instances. 자주 down하니 여러 개 시도.
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.cz",
    "https://nitter.unixfox.eu",
    "https://nitter.tiekoetter.com",
]

SOURCE_LABEL = "x_trump_nitter"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml,text/xml,*/*",
}


async def sync_truth_social(db: AsyncSession, limit: int = 20) -> dict:
    """nitter mirror에서 트럼프 X 최근 게시물 fetch + dedup INSERT.

    Returns:
        {"fetched": int, "inserted": int, "skipped": int,
         "instance": str?, "error": str?}
    """
    rss_text, used_instance = await _fetch_with_fallback()
    if not rss_text:
        return {
            "fetched": 0,
            "inserted": 0,
            "skipped": 0,
            "error": "모든 nitter instance fail (403/timeout/down)",
        }

    items = _parse_rss(rss_text)
    if not items:
        return {
            "fetched": 0,
            "inserted": 0,
            "skipped": 0,
            "instance": used_instance,
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
                author=NITTER_USER,
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
        "x_trump_nitter sync: instance=%s fetched=%d inserted=%d skipped=%d",
        used_instance,
        len(items),
        inserted,
        skipped,
    )
    return {
        "fetched": len(items),
        "inserted": inserted,
        "skipped": skipped,
        "instance": used_instance,
    }


async def _fetch_with_fallback() -> tuple[str | None, str | None]:
    """nitter 4-6 instance 순차 시도. 첫 valid RSS 응답 사용."""
    async with httpx.AsyncClient(timeout=10.0, headers=HEADERS, follow_redirects=True) as client:
        for instance in NITTER_INSTANCES:
            url = f"{instance}/{NITTER_USER}/rss"
            try:
                resp = await client.get(url)
            except Exception as e:  # noqa: BLE001
                logger.debug("nitter %s fail: %s", instance, e)
                continue
            if resp.status_code != 200:
                logger.debug("nitter %s status %d", instance, resp.status_code)
                continue
            body = resp.text
            if "<rss" not in body and "<feed" not in body:
                continue
            return body, instance
    return None, None


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
