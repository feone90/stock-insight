"""One-off cleanup for noisy news rows (NewsAPI broad-match leftovers).

Criterion: title must contain either the ticker (case-insensitive) or the
first significant word of stock.name. Anything else is treated as noise
(e.g. 'Laptop very slow.' tagged to MSFT because the body mentioned Windows).

Usage:
  cd backend
  uv run python -m scripts.clean_noisy_news            # dry-run
  uv run python -m scripts.clean_noisy_news --delete   # actually delete
"""

import asyncio
import re
import sys

from sqlalchemy import delete, select

from app.database import async_session
from app.models import News, Stock

# Strip common corporate suffixes when picking the first significant word.
_NAME_SUFFIX_RE = re.compile(
    r"\b(inc|corp|corporation|co|ltd|llc|plc|holdings|group|company)\.?\b",
    re.IGNORECASE,
)


def _name_words(name: str) -> list[str]:
    """Significant tokens from stock name. Skips short tokens (<3 chars) like
    'SK' which would match too aggressively across unrelated companies."""
    if not name:
        return []
    cleaned = _NAME_SUFFIX_RE.sub("", name)
    return [w for w in re.split(r"[\s,]+", cleaned) if len(w) >= 3]


def _is_noise(title: str, ticker: str, name_words: list[str]) -> bool:
    if not title:
        return True
    t = title.lower()
    if ticker and ticker.lower() in t:
        return False
    for w in name_words:
        if w.lower() in t:
            return False
    return True


async def main(delete_rows: bool) -> int:
    total_kept = 0
    total_noise = 0
    per_stock: list[tuple[str, str, int, int]] = []  # (ticker, filter_str, kept, noise)

    async with async_session() as db:
        stocks = (await db.execute(select(Stock))).scalars().all()
        for s in stocks:
            words = _name_words(s.name or "")
            news_rows = (
                await db.execute(select(News).where(News.stock_id == s.id))
            ).scalars().all()
            kept = 0
            noise_ids: list[int] = []
            for n in news_rows:
                if _is_noise(n.title or "", s.ticker, words):
                    noise_ids.append(n.id)
                else:
                    kept += 1
            total_kept += kept
            total_noise += len(noise_ids)
            filter_str = " | ".join([s.ticker] + words)
            per_stock.append((s.ticker, filter_str, kept, len(noise_ids)))

            if delete_rows and noise_ids:
                await db.execute(delete(News).where(News.id.in_(noise_ids)))

        if delete_rows:
            await db.commit()

    print("Per stock:")
    for ticker, filter_str, kept, noise in per_stock:
        print(f"  {ticker:8s} kept={kept:5d}  noise={noise:5d}   (filter: {filter_str})")
    print()
    print(f"Total kept: {total_kept}")
    print(f"Total noise: {total_noise}")
    if delete_rows:
        print(f"Deleted {total_noise} rows.")
    else:
        # ASCII only to avoid Windows cp949 console crash.
        print("(dry-run - no rows deleted. Pass --delete to actually clean.)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(delete_rows="--delete" in sys.argv)))
