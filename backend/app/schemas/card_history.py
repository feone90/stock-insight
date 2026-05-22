from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


EventDirection = Literal["positive", "negative", "mixed", "neutral"]
EventSourceType = Literal["price_move", "news", "catalyst"]


class AnalysisHistoryNews(BaseModel):
    title: str
    source: str
    impact: EventDirection
    summary: str
    published_at: datetime | None = None
    url: str | None = None


class AnalysisHistoryItem(BaseModel):
    date: date
    generated_at: datetime | None = None
    stance: Literal["BUY", "WATCH", "REJECT"] | None = None
    final_grade: str | None = None
    one_line: str
    thesis: str | None = None
    price_move: str | None = None
    news_count: int
    key_news: list[AnalysisHistoryNews]


class AnalysisHistoryResponse(BaseModel):
    ticker: str
    items: list[AnalysisHistoryItem]


class StockEventMarker(BaseModel):
    id: str
    date: date
    source_type: EventSourceType
    direction: EventDirection
    title: str
    summary: str
    keyword: str
    confidence: str | None = None
    source_label: str | None = None
    url: str | None = None
    analysis_date: date


class StockEventsResponse(BaseModel):
    ticker: str
    events: list[StockEventMarker]
