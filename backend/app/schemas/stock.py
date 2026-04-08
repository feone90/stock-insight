from pydantic import BaseModel


class Stock(BaseModel):
    ticker: str
    name: str
    market: str
    sector: str
    current_price: float
    change: float
    change_percent: float


class PriceRecord(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class KeywordDetail(BaseModel):
    keyword: str
    type: str
    detail: str
    source: str
    impact_level: str
    duration: str


class DailyKeyword(BaseModel):
    date: str
    keyword: str
    type: str


class Analysis(BaseModel):
    date: str
    period_type: str
    keywords: list[KeywordDetail]
    daily_keywords: list[DailyKeyword]
    summary: str
    feedback: str


class StatsInfo(BaseModel):
    market_cap: str
    per: float
    pbr: float
    dividend_yield: float
    high_52w: float
    low_52w: float


class StockDetailResponse(BaseModel):
    ticker: str
    name: str
    market: str
    sector: str
    current_price: float
    change: float
    change_percent: float
    is_favorite: bool
    stats: StatsInfo | None
