"""FRED collector — VIX / US10Y / FedFunds / 실업률 등 매크로 지표 수집.

FRED (Federal Reserve Economic Data) — st.louisfed.org 무료 공공 데이터.
Rate limit 120 req/min, 우리 일 1회 cron이면 충분.

수집 metric (`MACRO_SERIES`) 추가/제거는 dict 한 줄 — 카드 매크로 섹션이
`get_macro_context`에서 `factor` 키로 읽기 때문에 표기 키와 FRED series_id
모두 신경.

Spec 매크로 섹션은 카드 분석 시점에 macro_factors 테이블 읽음 (별도 sync
필요 없음 — 이 collector가 채우면 됨).
"""
from __future__ import annotations

import logging
from datetime import datetime

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.macro_factor import MacroFactor

logger = logging.getLogger(__name__)

_FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# (display key in macro_factors.factor) → FRED series_id
MACRO_SERIES: dict[str, str] = {
    "VIX": "VIXCLS",       # CBOE Volatility Index — 시장 공포 지수
    "US10Y": "DGS10",      # 10-year treasury yield (%)
    "FEDFUNDS": "FEDFUNDS",  # Fed funds 기준금리 (월별)
    "UNRATE": "UNRATE",    # US 실업률
}


async def sync_fred(db: AsyncSession) -> dict:
    """일일 FRED snapshot — 최근 관측 값 1건씩만 받아 macro_factors upsert.

    ON CONFLICT (factor, date) DO UPDATE: 같은 날 다시 돌려도 idempotent.
    """
    if not settings.fred_api_key:
        return {"fred_synced": 0, "error": "FRED_API_KEY 미설정"}

    synced = 0
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for factor, series_id in MACRO_SERIES.items():
            try:
                row = await _fetch_latest(client, series_id)
            except Exception as e:  # noqa: BLE001
                logger.warning("FRED fetch %s failed: %s", series_id, e)
                errors.append(f"{factor}:{e}")
                continue
            if row is None:
                continue
            stmt = pg_insert(MacroFactor).values(
                factor=factor,
                date=row["date"],
                value=row["value"],
                source="fred",
            ).on_conflict_do_update(
                index_elements=["factor", "date"],
                set_={"value": row["value"], "source": "fred"},
            )
            await db.execute(stmt)
            synced += 1
    await db.commit()
    out: dict = {"fred_synced": synced}
    if errors:
        out["errors"] = errors
    return out


async def _fetch_latest(client: httpx.AsyncClient, series_id: str) -> dict | None:
    """Pull the most recent non-NaN observation. FRED returns '.' for missing."""
    params = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 5,  # latest 5, skip '.' entries
    }
    r = await client.get(_FRED_BASE, params=params)
    r.raise_for_status()
    obs = r.json().get("observations", [])
    for o in obs:
        v = o.get("value")
        if v in (None, "", "."):
            continue
        try:
            value = float(v)
        except (TypeError, ValueError):
            continue
        try:
            d = datetime.strptime(o["date"], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        return {"date": d, "value": value}
    return None
