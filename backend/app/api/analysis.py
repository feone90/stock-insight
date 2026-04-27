from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.stocks import _get_or_register_stock
from app.database import get_db
from app.models import Analysis, Stock
from app.schemas.stock import AnalysisResponse

router = APIRouter(prefix="/api/stocks", tags=["analysis"])


@router.get("/{ticker}/analysis", response_model=AnalysisResponse)
async def stock_analysis(ticker: str, period: str = "weekly", db: AsyncSession = Depends(get_db)):
    stock = await _get_or_register_stock(ticker, db)

    analysis_result = await db.execute(
        select(Analysis)
        .options(selectinload(Analysis.keywords), selectinload(Analysis.daily_keywords))
        .where(Analysis.stock_id == stock.id, Analysis.period_type == period)
        .order_by(Analysis.date.desc())
        .limit(1)
    )
    analysis = analysis_result.scalar_one_or_none()
    if not analysis:
        return AnalysisResponse(
            date="", period_type=period, keywords=[],
            daily_keywords=[], summary="", feedback="",
        )

    return AnalysisResponse(
        date=analysis.date.isoformat(),
        period_type=analysis.period_type,
        keywords=[
            {"keyword": kw.keyword, "type": kw.type, "detail": kw.detail,
             "source": kw.source, "impact_level": kw.impact_level, "duration": kw.duration}
            for kw in analysis.keywords
        ],
        daily_keywords=[
            {"date": dk.date.isoformat(), "keyword": dk.keyword, "type": dk.type}
            for dk in analysis.daily_keywords
        ],
        summary=analysis.summary,
        feedback=analysis.feedback,
    )
