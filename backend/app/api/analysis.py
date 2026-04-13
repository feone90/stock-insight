from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Analysis, Stock

router = APIRouter(prefix="/api/stocks", tags=["analysis"])


@router.get("/{ticker}/analysis")
async def stock_analysis(ticker: str, period: str = "weekly", db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    analysis_result = await db.execute(
        select(Analysis)
        .options(selectinload(Analysis.keywords), selectinload(Analysis.daily_keywords))
        .where(Analysis.stock_id == stock.id, Analysis.period_type == period)
        .order_by(Analysis.date.desc())
        .limit(1)
    )
    analysis = analysis_result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="분석 데이터가 없습니다")

    return {
        "date": analysis.date.isoformat(),
        "period_type": analysis.period_type,
        "keywords": [
            {
                "keyword": kw.keyword,
                "type": kw.type,
                "detail": kw.detail,
                "source": kw.source,
                "impact_level": kw.impact_level,
                "duration": kw.duration,
            }
            for kw in analysis.keywords
        ],
        "daily_keywords": [
            {
                "date": dk.date.isoformat(),
                "keyword": dk.keyword,
                "type": dk.type,
            }
            for dk in analysis.daily_keywords
        ],
        "summary": analysis.summary,
        "feedback": analysis.feedback,
    }
