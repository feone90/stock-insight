from datetime import datetime

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Stock
from app.models.disclosure import Disclosure


async def fetch_dart_disclosures(corp_code: str) -> dict:
    """DART API로 공시 목록 조회."""
    url = "https://opendart.fss.or.kr/api/list.json"
    params = {
        "crtfc_key": settings.dart_api_key,
        "corp_code": corp_code,
        "page_count": "30",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def sync_disclosures(db: AsyncSession, stock: Stock) -> dict:
    """종목의 공시를 동기화한다. KR 종목만 해당."""
    if stock.market not in ("KRX", "KOSPI", "KOSDAQ"):
        return {"disclosures_synced": 0}

    if not settings.dart_api_key:
        return {"disclosures_synced": 0, "error": "DART API 키 미설정"}

    if not stock.dart_code:
        return {"disclosures_synced": 0, "error": "DART 기업코드 미설정"}

    try:
        data = await fetch_dart_disclosures(stock.dart_code)
    except Exception as e:
        return {"disclosures_synced": 0, "error": f"공시 조회 실패: {e}"}

    if data.get("status") != "000":
        return {"disclosures_synced": 0, "error": f"DART API 오류: {data.get('message', 'unknown')}"}

    items = data.get("list", [])
    count = 0
    for item in items:
        rcept_dt = item.get("rcept_dt", "")
        try:
            disclosed_at = datetime.strptime(rcept_dt, "%Y%m%d")
        except ValueError:
            disclosed_at = datetime.now()

        stmt = insert(Disclosure).values(
            stock_id=stock.id,
            title=item.get("report_nm", ""),
            content=None,
            disclosure_type=item.get("pblntf_ty", "기타"),
            disclosed_at=disclosed_at,
        ).on_conflict_do_nothing(constraint="uq_disclosure_stock_title_date")
        result = await db.execute(stmt)
        if result.rowcount > 0:
            count += 1

    await db.commit()
    return {"disclosures_synced": count}
