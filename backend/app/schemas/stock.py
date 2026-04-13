"""API 응답 스키마."""

from pydantic import BaseModel


class StockResponse(BaseModel):
    ticker: str
    name: str
    market: str
    sector: str | None = None
    current_price: float | None = None
    change: float | None = None
    change_percent: float | None = None


class StatsResponse(BaseModel):
    market_cap: str
    per: float
    pbr: float
    dividend_yield: float
    high_52w: float
    low_52w: float


class StockDetailResponse(StockResponse):
    is_favorite: bool = False
    stats: StatsResponse | None = None


class PriceResponse(BaseModel):
    date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = None


class NewsResponse(BaseModel):
    title: str
    source: str | None = None
    url: str | None = None
    published_at: str


class DisclosureResponse(BaseModel):
    title: str
    disclosure_type: str | None = None
    disclosed_at: str


class KeywordResponse(BaseModel):
    keyword: str
    type: str
    detail: str
    source: str
    impact_level: str
    duration: str


class DailyKeywordResponse(BaseModel):
    date: str
    keyword: str
    type: str


class AnalysisResponse(BaseModel):
    date: str
    period_type: str
    keywords: list[KeywordResponse]
    daily_keywords: list[DailyKeywordResponse]
    summary: str
    feedback: str


class SyncResult(BaseModel):
    status: str = "ok"
    ticker: str
    synced: dict
    errors: list[str]


class SyncAllResult(BaseModel):
    status: str = "ok"
    stocks_synced: list[str]
    global_synced: bool = True
    total_synced: dict
    errors: list[str]


class SyncGlobalResult(BaseModel):
    status: str = "ok"
    synced: dict
    errors: list[str]


class ExchangeRateResponse(BaseModel):
    date: str
    currency_pair: str
    rate: float


class FavoriteActionResponse(BaseModel):
    status: str
    ticker: str
