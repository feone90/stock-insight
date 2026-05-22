from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class DailyPriceDriverResponse(BaseModel):
    id: int
    ticker: str
    trade_date: date
    direction: Literal["positive", "negative", "mixed", "neutral"]
    keywords: list[str]
    summary: str
    evidence: dict
    confidence: str | None = None
    model_version: str
    created_at: datetime | None = None


class DailyDriverRunResult(BaseModel):
    status: str
    processed: int
    created: int
    skipped: int
    errors: list[str]
    rows: list[DailyPriceDriverResponse] = []
