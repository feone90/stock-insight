"""Truth Social crawler — 트럼프 발언 fetch + DB dedup INSERT.

Source: truthsocial.com Mastodon-compatible API (비공식, unstable).
가족 dev에서는 안정성 < 작동. 실패 시 collector 패턴으로 dict 반환 (no exception).

LLM 분석(political_signal_analyzer)은 별도 step — 이 모듈은 raw 게시물만
저장. 모든 게시물을 LLM 통과시키지 않고 is_market_relevant 분석으로 noise
필터링 후 카드에 노출.
"""
from __future__ import annotations

import html as html_lib
import logging
import re
from datetime import datetime

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.political_signal import PoliticalSignal

logger = logging.getLogger(__name__)

# Truth Social Mastodon-compatible API. account id는 @realDonaldTrump 고유 ID
# (공개 정보). public statuses는 인증 없이 fetch 가능.
TRUMP_ACCOUNT_ID = "107780257626128497"
TS_STATUSES_URL = (
    f"https://truthsocial.com/api/v1/accounts/{TRUMP_ACCOUNT_ID}/statuses"
)

# 일반 브라우저 UA — Cloudflare 차단 회피 (간단 수준)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


async def sync_truth_social(db: AsyncSession, limit: int = 20) -> dict:
    """최근 statuses fetch + ON CONFLICT (source,source_post_id) DO NOTHING.

    Returns:
        {"fetched": int, "inserted": int, "skipped": int, "error": str?}
    """
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=HEADERS) as client:
            resp = await client.get(
                TS_STATUSES_URL,
                params={"limit": limit, "exclude_replies": "true"},
            )
            resp.raise_for_status()
            statuses = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("truth_social fetch failed: %s", e)
        return {
            "fetched": 0,
            "inserted": 0,
            "skipped": 0,
            "error": f"fetch failed: {e}",
        }

    if not isinstance(statuses, list):
        return {
            "fetched": 0,
            "inserted": 0,
            "skipped": 0,
            "error": "unexpected response shape (expected list)",
        }

    inserted = 0
    skipped = 0
    for status in statuses:
        post_id = status.get("id")
        if not post_id:
            continue

        content_html = status.get("content") or ""
        content = _strip_html(content_html)
        if not content.strip():
            skipped += 1
            continue

        try:
            posted_at_str = status.get("created_at", "").replace("Z", "+00:00")
            posted_at = datetime.fromisoformat(posted_at_str)
            posted_at = posted_at.replace(tzinfo=None)  # naive UTC
        except Exception:
            posted_at = datetime.utcnow()

        stmt = (
            pg_insert(PoliticalSignal)
            .values(
                source="truth_social",
                source_post_id=str(post_id),
                author="realDonaldTrump",
                posted_at=posted_at,
                content=content[:4000],
                content_lang=status.get("language") or "en",
                url=status.get("url"),
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
        "truth_social sync: fetched=%d inserted=%d skipped=%d",
        len(statuses),
        inserted,
        skipped,
    )
    return {
        "fetched": len(statuses),
        "inserted": inserted,
        "skipped": skipped,
    }


def _strip_html(html: str) -> str:
    """Mastodon `<p>...</p><br>...` 등 minimal HTML → plain text."""
    s = re.sub(r"<br\s*/?>", "\n", html)
    s = re.sub(r"</p>\s*<p>", "\n\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return html_lib.unescape(s).strip()
