from fastapi import APIRouter, HTTPException

from app.mocks.analysis import get_analysis

router = APIRouter(prefix="/api/stocks", tags=["analysis"])


@router.get("/{ticker}/analysis")
def stock_analysis(ticker: str, period: str = "weekly"):
    analysis = get_analysis(ticker)
    if not analysis:
        raise HTTPException(status_code=404, detail="분석 데이터가 없습니다")
    return analysis
