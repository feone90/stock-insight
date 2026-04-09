from datetime import date

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exchange_rate import ExchangeRate


CURRENCY_PAIRS = {
    "KRW": "USD/KRW",
    "EUR": "USD/EUR",
    "JPY": "USD/JPY",
}


async def fetch_exchange_rates() -> dict:
    """ExchangeRate API 호출."""
    url = "https://open.er-api.com/v6/latest/USD"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


async def sync_exchange_rates(db: AsyncSession) -> dict:
    """주요 통화 환율을 동기화한다."""
    try:
        data = await fetch_exchange_rates()
    except Exception as e:
        return {"exchange_rates_synced": 0, "error": f"환율 조회 실패: {e}"}

    if data.get("result") != "success":
        return {"exchange_rates_synced": 0, "error": "ExchangeRate API 오류"}

    rates = data.get("rates", {})
    today = date.today()
    count = 0

    for currency_code, pair_name in CURRENCY_PAIRS.items():
        rate_value = rates.get(currency_code)
        if rate_value is None:
            continue

        stmt = insert(ExchangeRate).values(
            date=today,
            currency_pair=pair_name,
            rate=float(rate_value),
        ).on_conflict_do_update(
            constraint="uq_rate_date_pair",
            set_={"rate": float(rate_value)},
        )
        await db.execute(stmt)
        count += 1

    await db.commit()
    return {"exchange_rates_synced": count}
