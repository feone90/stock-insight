# Phase 1 실제 데이터 연동 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** StockInsight에 실제 외부 데이터 소스(주가, 재무지표, 뉴스, 공시, 환율)를 연동하고, 수동 동기화 버튼으로 데이터를 수집한다.

**Architecture:** Flat collector 모듈 패턴. 각 데이터 소스별 독립 collector 모듈(5개)이 외부 API를 호출하여 DB에 저장. Admin API 라우터가 collector를 직접 호출. 프론트엔드에 종목별/전체 동기화 버튼 추가.

**Tech Stack:** FastAPI, SQLAlchemy async, yfinance, FinanceDataReader, httpx, Alembic, Next.js, shadcn/ui

**Spec:** `docs/superpowers/specs/2026-04-09-phase1-data-integration-design.md`

---

## File Structure

### Backend — 새로 생성

| 파일 | 역할 |
|------|------|
| `backend/app/models/news.py` | News ORM 모델 |
| `backend/app/models/disclosure.py` | Disclosure ORM 모델 |
| `backend/app/models/financial.py` | Financial ORM 모델 |
| `backend/app/models/exchange_rate.py` | ExchangeRate ORM 모델 |
| `backend/app/collectors/__init__.py` | Collector 패키지 |
| `backend/app/collectors/stock_price.py` | 주가 수집 (yfinance + FDR) |
| `backend/app/collectors/financials.py` | 재무지표 수집 |
| `backend/app/collectors/news.py` | 뉴스 수집 (Naver API) |
| `backend/app/collectors/disclosure.py` | 공시 수집 (DART API) |
| `backend/app/collectors/exchange_rate.py` | 환율 수집 |
| `backend/app/api/admin.py` | Admin sync API 라우터 |
| `backend/tests/test_collectors.py` | Collector 단위 테스트 |
| `backend/tests/test_admin_api.py` | Admin API 통합 테스트 |

### Backend — 수정

| 파일 | 변경 내용 |
|------|-----------|
| `backend/app/models/__init__.py` | 새 모델 4개 re-export 추가 |
| `backend/app/models/stock.py` | `dart_code` 컬럼 추가 |
| `backend/app/config.py` | API 키 환경변수 3개 추가 |
| `backend/.env.example` | API 키 템플릿 추가 |
| `backend/app/main.py` | admin 라우터 등록 |
| `backend/app/api/stocks.py` | stats를 financials 테이블에서 조회 |
| `backend/requirements.txt` | yfinance, finance-datareader 추가 |

### Frontend — 수정

| 파일 | 변경 내용 |
|------|-----------|
| `frontend/src/services/api.ts` | syncStock, syncAll 함수 추가 |
| `frontend/src/components/stock/stock-header.tsx` | "동기화" 버튼 추가 |
| `frontend/src/components/layout/top-nav.tsx` | "전체 동기화" 버튼 추가 |

---

### Task 1: 새 DB 모델 4개 + Stock 모델 변경 + Alembic 마이그레이션

**Files:**
- Create: `backend/app/models/news.py`
- Create: `backend/app/models/disclosure.py`
- Create: `backend/app/models/financial.py`
- Create: `backend/app/models/exchange_rate.py`
- Modify: `backend/app/models/stock.py:10-23`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Create `backend/app/models/news.py`**

```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.stock import Base


class News(Base):
    __tablename__ = "news"
    __table_args__ = (UniqueConstraint("stock_id", "url", name="uq_news_stock_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    title: Mapped[str] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(1000))
    published_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 2: Create `backend/app/models/disclosure.py`**

```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.stock import Base


class Disclosure(Base):
    __tablename__ = "disclosures"
    __table_args__ = (
        UniqueConstraint("stock_id", "title", "disclosed_at", name="uq_disclosure_stock_title_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    title: Mapped[str] = mapped_column(String(500))
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    disclosure_type: Mapped[str] = mapped_column(String(50))
    disclosed_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 3: Create `backend/app/models/financial.py`**

```python
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.stock import Base


class Financial(Base):
    __tablename__ = "financials"
    __table_args__ = (UniqueConstraint("stock_id", "period", name="uq_financial_stock_period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    period: Mapped[str] = mapped_column(String(20))
    period_type: Mapped[str] = mapped_column(String(20))
    revenue: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    operating_profit: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    net_income: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    per: Mapped[float | None] = mapped_column(Float, nullable=True)
    pbr: Mapped[float | None] = mapped_column(Float, nullable=True)
    roe: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 4: Create `backend/app/models/exchange_rate.py`**

```python
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.stock import Base


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("date", "currency_pair", name="uq_rate_date_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date)
    currency_pair: Mapped[str] = mapped_column(String(10))
    rate: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 5: Add `dart_code` to Stock model in `backend/app/models/stock.py`**

기존 `created_at` 줄 위에 추가:

```python
dart_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
```

- [ ] **Step 6: Update `backend/app/models/__init__.py`**

```python
from app.models.stock import Base, Stock
from app.models.price import PriceHistory
from app.models.analysis import Analysis, DailyKeyword, KeywordDetail
from app.models.favorite import Favorite
from app.models.news import News
from app.models.disclosure import Disclosure
from app.models.financial import Financial
from app.models.exchange_rate import ExchangeRate

__all__ = [
    "Base",
    "Stock",
    "PriceHistory",
    "Analysis",
    "KeywordDetail",
    "DailyKeyword",
    "Favorite",
    "News",
    "Disclosure",
    "Financial",
    "ExchangeRate",
]
```

- [ ] **Step 7: Add yfinance and finance-datareader to `backend/requirements.txt`**

기존 내용 끝에 추가:

```
yfinance
finance-datareader
```

- [ ] **Step 8: Install new packages**

Run: `cd backend && source venv/bin/activate && pip install yfinance finance-datareader`
Expected: 설치 성공

- [ ] **Step 9: Generate Alembic migration**

Run: `cd backend && source venv/bin/activate && alembic revision --autogenerate -m "add news disclosures financials exchange_rates tables and stock dart_code"`
Expected: 마이그레이션 파일 생성

- [ ] **Step 10: Run migration**

Run: `cd backend && source venv/bin/activate && alembic upgrade head`
Expected: 테이블 4개 생성 + stocks 테이블에 dart_code 컬럼 추가

- [ ] **Step 11: Verify migration**

Run: `cd backend && source venv/bin/activate && python -c "from app.models import News, Disclosure, Financial, ExchangeRate; print('Models imported OK')"`
Expected: `Models imported OK`

- [ ] **Step 12: Commit**

```bash
git add backend/app/models/ backend/requirements.txt backend/alembic/
git commit -m "feat: add News, Disclosure, Financial, ExchangeRate models + dart_code column"
```

---

### Task 2: Settings 환경변수 + .env.example 업데이트

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Update `backend/app/config.py`**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:admin123!@localhost:5432/stockinsight"
    dart_api_key: str = ""
    naver_client_id: str = ""
    naver_client_secret: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **Step 2: Update `backend/.env.example`**

기존 내용 끝에 추가:

```env
DART_API_KEY=your_dart_api_key_here
NAVER_CLIENT_ID=your_naver_client_id_here
NAVER_CLIENT_SECRET=your_naver_client_secret_here
```

- [ ] **Step 3: Write test for settings loading**

`backend/tests/test_collectors.py` 파일 생성:

```python
from app.config import Settings


def test_settings_defaults():
    s = Settings(database_url="postgresql+asyncpg://test:test@localhost/test")
    assert s.dart_api_key == ""
    assert s.naver_client_id == ""
    assert s.naver_client_secret == ""
```

- [ ] **Step 4: Run test**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_collectors.py::test_settings_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/.env.example backend/tests/test_collectors.py
git commit -m "feat: add API key settings for DART and Naver"
```

---

### Task 3: stock_price collector (yfinance + FinanceDataReader)

**Files:**
- Create: `backend/app/collectors/__init__.py`
- Create: `backend/app/collectors/stock_price.py`
- Modify: `backend/tests/test_collectors.py`

- [ ] **Step 1: Create `backend/app/collectors/__init__.py`**

```python
```

(빈 파일)

- [ ] **Step 2: Write failing test for stock_price collector**

`backend/tests/test_collectors.py`에 추가:

```python
import pytest
import pytest_asyncio
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
import pandas as pd

from app.collectors.stock_price import sync_prices
from app.models import Stock, PriceHistory


@pytest.mark.asyncio
async def test_sync_prices_us_stock(db):
    """US 종목 주가 동기화 — yfinance mock 사용"""
    # Arrange: Stock 조회
    from sqlalchemy import select
    result = await db.execute(select(Stock).where(Stock.ticker == "AAPL"))
    stock = result.scalar_one()

    today = date.today()
    dates = pd.date_range(end=today, periods=3, freq="B")
    mock_df = pd.DataFrame({
        "Open": [150.0, 151.0, 152.0],
        "High": [155.0, 156.0, 157.0],
        "Low": [149.0, 150.0, 151.0],
        "Close": [153.0, 154.0, 155.0],
        "Volume": [1000000, 1100000, 1200000],
    }, index=dates)

    with patch("app.collectors.stock_price.fetch_us_prices", return_value=mock_df):
        result = await sync_prices(db, stock)

    assert result["prices_synced"] >= 0
    assert "error" not in result


@pytest.mark.asyncio
async def test_sync_prices_kr_stock(db):
    """KR 종목 주가 동기화 — FDR mock 사용"""
    from sqlalchemy import select
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()

    today = date.today()
    dates = pd.date_range(end=today, periods=3, freq="B")
    mock_df = pd.DataFrame({
        "Open": [71000, 71500, 72000],
        "High": [72000, 72500, 73000],
        "Low": [70500, 71000, 71500],
        "Close": [71500, 72000, 72500],
        "Volume": [5000000, 5500000, 6000000],
    }, index=dates)

    with patch("app.collectors.stock_price.fetch_kr_prices", return_value=mock_df):
        result = await sync_prices(db, stock)

    assert result["prices_synced"] >= 0
    assert "error" not in result
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_collectors.py::test_sync_prices_us_stock -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.collectors.stock_price'`

- [ ] **Step 4: Implement `backend/app/collectors/stock_price.py`**

```python
import asyncio
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PriceHistory, Stock


def fetch_us_prices(ticker: str, start: str) -> pd.DataFrame:
    """yfinance로 US 주가 조회 (동기 함수)."""
    import yfinance as yf
    df = yf.download(ticker, start=start, progress=False, auto_adjust=True)
    return df


def fetch_kr_prices(ticker: str, start: str) -> pd.DataFrame:
    """FinanceDataReader로 KR 주가 조회 (동기 함수)."""
    import FinanceDataReader as fdr
    df = fdr.DataReader(ticker, start)
    return df


async def sync_prices(db: AsyncSession, stock: Stock) -> dict:
    """종목의 최근 1년 주가를 동기화한다."""
    start = (date.today() - timedelta(days=365)).isoformat()

    try:
        if stock.market in ("NYSE", "NASDAQ"):
            df = await asyncio.to_thread(fetch_us_prices, stock.ticker, start)
        else:
            df = await asyncio.to_thread(fetch_kr_prices, stock.ticker, start)
    except Exception as e:
        return {"prices_synced": 0, "error": f"주가 조회 실패: {e}"}

    if df is None or df.empty:
        return {"prices_synced": 0, "error": "주가 데이터 없음"}

    count = 0
    for idx, row in df.iterrows():
        dt = idx.date() if hasattr(idx, "date") else idx
        stmt = insert(PriceHistory).values(
            stock_id=stock.id,
            date=dt,
            open=float(row.get("Open", 0)),
            high=float(row.get("High", 0)),
            low=float(row.get("Low", 0)),
            close=float(row.get("Close", 0)),
            volume=int(row.get("Volume", 0)),
        ).on_conflict_do_nothing(constraint="uq_stock_date")
        result = await db.execute(stmt)
        if result.rowcount > 0:
            count += 1

    # Stock 최신 종가 업데이트
    if not df.empty:
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else df.iloc[0]
        stock.current_price = float(latest["Close"])
        stock.change = float(latest["Close"] - prev["Close"])
        if prev["Close"] != 0:
            stock.change_percent = round(float((latest["Close"] - prev["Close"]) / prev["Close"] * 100), 2)
        db.add(stock)

    await db.commit()
    return {"prices_synced": count}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_collectors.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/collectors/ backend/tests/test_collectors.py
git commit -m "feat: add stock_price collector with yfinance + FDR support"
```

---

### Task 4: financials collector

**Files:**
- Create: `backend/app/collectors/financials.py`
- Modify: `backend/tests/test_collectors.py`

- [ ] **Step 1: Write failing test**

`backend/tests/test_collectors.py`에 추가:

```python
from app.collectors.financials import sync_financials


@pytest.mark.asyncio
async def test_sync_financials_us_stock(db):
    """US 종목 재무지표 동기화 — yfinance mock"""
    from sqlalchemy import select
    result = await db.execute(select(Stock).where(Stock.ticker == "AAPL"))
    stock = result.scalar_one()

    mock_info = {
        "trailingPE": 28.5,
        "priceToBook": 45.2,
        "returnOnEquity": 0.152,
        "dividendYield": 0.006,
        "marketCap": 3000000000000,
        "totalRevenue": 390000000000,
        "operatingIncome": 120000000000,
        "netIncome": 95000000000,
    }

    with patch("app.collectors.financials.fetch_us_financials", return_value=mock_info):
        result = await sync_financials(db, stock)

    assert result["financials_synced"] >= 0
    assert "error" not in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_collectors.py::test_sync_financials_us_stock -v`
Expected: FAIL

- [ ] **Step 3: Implement `backend/app/collectors/financials.py`**

```python
import asyncio
from datetime import date

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Stock
from app.models.financial import Financial


def fetch_us_financials(ticker: str) -> dict:
    """yfinance로 US 재무지표 조회."""
    import yfinance as yf
    t = yf.Ticker(ticker)
    return t.info


async def fetch_kr_financials(ticker: str) -> dict:
    """DART API로 KR 재무지표 조회."""
    import httpx
    if not settings.dart_api_key:
        return {}
    # DART 단일회사 재무제표 (최근 분기)
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"
    year = date.today().year
    params = {
        "crtfc_key": settings.dart_api_key,
        "corp_code": ticker,  # 실제로는 dart_code를 사용
        "bsns_year": str(year - 1),
        "reprt_code": "11011",  # 사업보고서
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        if resp.status_code == 200:
            return resp.json()
    return {}


async def sync_financials(db: AsyncSession, stock: Stock) -> dict:
    """종목의 재무지표를 동기화한다."""
    period = f"{date.today().year}Q0"  # 최신 (TTM)

    try:
        if stock.market in ("NYSE", "NASDAQ"):
            info = await asyncio.to_thread(fetch_us_financials, stock.ticker)
            if not info:
                return {"financials_synced": 0, "error": "재무 데이터 없음"}

            stmt = insert(Financial).values(
                stock_id=stock.id,
                period=period,
                period_type="ttm",
                revenue=int(info.get("totalRevenue", 0)) if info.get("totalRevenue") else None,
                operating_profit=int(info.get("operatingIncome", 0)) if info.get("operatingIncome") else None,
                net_income=int(info.get("netIncome", 0)) if info.get("netIncome") else None,
                per=info.get("trailingPE"),
                pbr=info.get("priceToBook"),
                roe=round(info.get("returnOnEquity", 0) * 100, 2) if info.get("returnOnEquity") else None,
                dividend_yield=round(info.get("dividendYield", 0) * 100, 2) if info.get("dividendYield") else None,
                market_cap=info.get("marketCap"),
            ).on_conflict_do_update(
                constraint="uq_financial_stock_period",
                set_={
                    "revenue": int(info.get("totalRevenue", 0)) if info.get("totalRevenue") else None,
                    "operating_profit": int(info.get("operatingIncome", 0)) if info.get("operatingIncome") else None,
                    "net_income": int(info.get("netIncome", 0)) if info.get("netIncome") else None,
                    "per": info.get("trailingPE"),
                    "pbr": info.get("priceToBook"),
                    "roe": round(info.get("returnOnEquity", 0) * 100, 2) if info.get("returnOnEquity") else None,
                    "dividend_yield": round(info.get("dividendYield", 0) * 100, 2) if info.get("dividendYield") else None,
                    "market_cap": info.get("marketCap"),
                },
            )
            await db.execute(stmt)
        else:
            # KR: DART API — dart_code 필요
            if not stock.dart_code or not settings.dart_api_key:
                return {"financials_synced": 0, "error": "DART API 키 또는 기업코드 미설정"}
            data = await fetch_kr_financials(stock.dart_code)
            if not data or data.get("status") != "000":
                return {"financials_synced": 0, "error": "DART 재무데이터 조회 실패"}
            # DART 응답 파싱은 Phase 1에서는 기본 항목만
            # 실제 파싱 로직은 구현 시 DART 응답 구조에 맞게 조정
            return {"financials_synced": 0, "error": "KR 재무지표 파싱 미구현 (Phase 1 범위 축소)"}

        await db.commit()
        return {"financials_synced": 1}

    except Exception as e:
        return {"financials_synced": 0, "error": f"재무지표 동기화 실패: {e}"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_collectors.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/collectors/financials.py backend/tests/test_collectors.py
git commit -m "feat: add financials collector with yfinance support"
```

---

### Task 5: news collector (Naver News API)

**Files:**
- Create: `backend/app/collectors/news.py`
- Modify: `backend/tests/test_collectors.py`

- [ ] **Step 1: Write failing test**

`backend/tests/test_collectors.py`에 추가:

```python
from app.collectors.news import sync_news


@pytest.mark.asyncio
async def test_sync_news(db):
    """뉴스 동기화 — Naver API mock"""
    from sqlalchemy import select
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()

    mock_response = {
        "items": [
            {
                "title": "<b>삼성전자</b> HBM 수주 확대",
                "link": "https://news.example.com/1",
                "pubDate": "Wed, 09 Apr 2026 10:00:00 +0900",
            },
            {
                "title": "<b>삼성전자</b> 실적 전망",
                "link": "https://news.example.com/2",
                "pubDate": "Tue, 08 Apr 2026 09:00:00 +0900",
            },
        ]
    }

    with patch("app.collectors.news.fetch_naver_news", return_value=mock_response):
        result = await sync_news(db, stock)

    assert result["news_synced"] >= 0
    assert "error" not in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_collectors.py::test_sync_news -v`
Expected: FAIL

- [ ] **Step 3: Implement `backend/app/collectors/news.py`**

```python
import re
from datetime import datetime
from email.utils import parsedate_to_datetime

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Stock
from app.models.news import News


def strip_html(text: str) -> str:
    """HTML 태그 제거."""
    return re.sub(r"<[^>]+>", "", text)


async def fetch_naver_news(query: str, display: int = 50) -> dict:
    """Naver News API 호출."""
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": settings.naver_client_id,
        "X-Naver-Client-Secret": settings.naver_client_secret,
    }
    params = {"query": query, "display": display, "sort": "date"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()


async def sync_news(db: AsyncSession, stock: Stock) -> dict:
    """종목 관련 뉴스를 동기화한다."""
    if not settings.naver_client_id or not settings.naver_client_secret:
        return {"news_synced": 0, "error": "Naver API 키 미설정"}

    try:
        data = await fetch_naver_news(stock.name)
    except Exception as e:
        return {"news_synced": 0, "error": f"뉴스 조회 실패: {e}"}

    items = data.get("items", [])
    count = 0
    for item in items:
        try:
            pub_date = parsedate_to_datetime(item["pubDate"])
        except Exception:
            pub_date = datetime.now()

        stmt = insert(News).values(
            stock_id=stock.id,
            title=strip_html(item.get("title", "")),
            source="네이버뉴스",
            url=item.get("link", ""),
            published_at=pub_date,
        ).on_conflict_do_nothing(constraint="uq_news_stock_url")
        result = await db.execute(stmt)
        if result.rowcount > 0:
            count += 1

    await db.commit()
    return {"news_synced": count}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_collectors.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/collectors/news.py backend/tests/test_collectors.py
git commit -m "feat: add news collector with Naver News API"
```

---

### Task 6: disclosure collector (DART API)

**Files:**
- Create: `backend/app/collectors/disclosure.py`
- Modify: `backend/tests/test_collectors.py`

- [ ] **Step 1: Write failing test**

`backend/tests/test_collectors.py`에 추가:

```python
from app.collectors.disclosure import sync_disclosures


@pytest.mark.asyncio
async def test_sync_disclosures_kr_stock(db):
    """KR 종목 공시 동기화 — DART API mock"""
    from sqlalchemy import select
    result = await db.execute(select(Stock).where(Stock.ticker == "005930"))
    stock = result.scalar_one()
    stock.dart_code = "00126380"  # 삼성전자 DART 고유번호

    mock_response = {
        "status": "000",
        "list": [
            {
                "report_nm": "분기보고서 (2026.03)",
                "rcept_dt": "20260401",
                "flr_nm": "삼성전자",
            },
            {
                "report_nm": "주요사항보고서(자기주식취득결정)",
                "rcept_dt": "20260325",
                "flr_nm": "삼성전자",
            },
        ],
    }

    with patch("app.collectors.disclosure.fetch_dart_disclosures", return_value=mock_response):
        result = await sync_disclosures(db, stock)

    assert result["disclosures_synced"] >= 0
    assert "error" not in result


@pytest.mark.asyncio
async def test_sync_disclosures_us_stock_skip(db):
    """US 종목은 공시 수집 스킵"""
    from sqlalchemy import select
    result = await db.execute(select(Stock).where(Stock.ticker == "AAPL"))
    stock = result.scalar_one()

    result = await sync_disclosures(db, stock)
    assert result["disclosures_synced"] == 0
    assert "스킵" in result.get("error", "") or "skip" in result.get("error", "").lower() or "error" not in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_collectors.py::test_sync_disclosures_kr_stock -v`
Expected: FAIL

- [ ] **Step 3: Implement `backend/app/collectors/disclosure.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_collectors.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/collectors/disclosure.py backend/tests/test_collectors.py
git commit -m "feat: add disclosure collector with DART API"
```

---

### Task 7: exchange_rate collector

**Files:**
- Create: `backend/app/collectors/exchange_rate.py`
- Modify: `backend/tests/test_collectors.py`

- [ ] **Step 1: Write failing test**

`backend/tests/test_collectors.py`에 추가:

```python
from app.collectors.exchange_rate import sync_exchange_rates


@pytest.mark.asyncio
async def test_sync_exchange_rates(db):
    """환율 동기화 — ExchangeRate API mock"""
    mock_response = {
        "result": "success",
        "rates": {
            "KRW": 1350.25,
            "EUR": 0.92,
            "JPY": 154.30,
        },
    }

    with patch("app.collectors.exchange_rate.fetch_exchange_rates", return_value=mock_response):
        result = await sync_exchange_rates(db)

    assert result["exchange_rates_synced"] >= 0
    assert "error" not in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_collectors.py::test_sync_exchange_rates -v`
Expected: FAIL

- [ ] **Step 3: Implement `backend/app/collectors/exchange_rate.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_collectors.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/collectors/exchange_rate.py backend/tests/test_collectors.py
git commit -m "feat: add exchange_rate collector"
```

---

### Task 8: Admin sync API 라우터

**Files:**
- Create: `backend/app/api/admin.py`
- Modify: `backend/app/main.py:7-30`
- Create: `backend/tests/test_admin_api.py`

- [ ] **Step 1: Write failing test**

`backend/tests/test_admin_api.py` 생성:

```python
import pytest
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_sync_stock(client):
    """종목별 동기화 API"""
    mock_results = {
        "prices": {"prices_synced": 10},
        "financials": {"financials_synced": 1},
        "news": {"news_synced": 5},
        "disclosures": {"disclosures_synced": 3},
    }

    with patch("app.api.admin.sync_prices", new_callable=AsyncMock, return_value=mock_results["prices"]), \
         patch("app.api.admin.sync_financials", new_callable=AsyncMock, return_value=mock_results["financials"]), \
         patch("app.api.admin.sync_news", new_callable=AsyncMock, return_value=mock_results["news"]), \
         patch("app.api.admin.sync_disclosures", new_callable=AsyncMock, return_value=mock_results["disclosures"]):
        resp = await client.post("/api/admin/sync/stock/005930")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "synced" in data


@pytest.mark.asyncio
async def test_sync_stock_not_found(client):
    """존재하지 않는 종목 동기화 시 404"""
    resp = await client.post("/api/admin/sync/stock/INVALID")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sync_global(client):
    """글로벌 동기화 API"""
    mock_result = {"exchange_rates_synced": 3}

    with patch("app.api.admin.sync_exchange_rates", new_callable=AsyncMock, return_value=mock_result):
        resp = await client.post("/api/admin/sync/global")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_admin_api.py::test_sync_stock -v`
Expected: FAIL

- [ ] **Step 3: Implement `backend/app/api/admin.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Favorite, Stock
from app.collectors.stock_price import sync_prices
from app.collectors.financials import sync_financials
from app.collectors.news import sync_news
from app.collectors.disclosure import sync_disclosures
from app.collectors.exchange_rate import sync_exchange_rates

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/sync/stock/{ticker}")
async def sync_stock(ticker: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    prices_result = await sync_prices(db, stock)
    financials_result = await sync_financials(db, stock)
    news_result = await sync_news(db, stock)
    disclosures_result = await sync_disclosures(db, stock)

    errors = []
    for r in [prices_result, financials_result, news_result, disclosures_result]:
        if "error" in r:
            errors.append(r["error"])

    return {
        "status": "ok",
        "ticker": ticker,
        "synced": {
            "prices": prices_result.get("prices_synced", 0),
            "financials": financials_result.get("financials_synced", 0),
            "news": news_result.get("news_synced", 0),
            "disclosures": disclosures_result.get("disclosures_synced", 0),
        },
        "errors": errors,
    }


@router.post("/sync/global")
async def sync_global(db: AsyncSession = Depends(get_db)):
    rates_result = await sync_exchange_rates(db)

    errors = []
    if "error" in rates_result:
        errors.append(rates_result["error"])

    return {
        "status": "ok",
        "synced": {
            "exchange_rates": rates_result.get("exchange_rates_synced", 0),
        },
        "errors": errors,
    }


@router.post("/sync/all")
async def sync_all(db: AsyncSession = Depends(get_db)):
    # 즐겨찾기 종목 조회
    fav_result = await db.execute(
        select(Stock).join(Favorite, Favorite.stock_id == Stock.id)
    )
    stocks = fav_result.scalars().all()

    total = {"prices": 0, "financials": 0, "news": 0, "disclosures": 0, "exchange_rates": 0}
    errors = []
    tickers_synced = []

    for stock in stocks:
        tickers_synced.append(stock.ticker)

        prices_result = await sync_prices(db, stock)
        financials_result = await sync_financials(db, stock)
        news_result = await sync_news(db, stock)
        disclosures_result = await sync_disclosures(db, stock)

        total["prices"] += prices_result.get("prices_synced", 0)
        total["financials"] += financials_result.get("financials_synced", 0)
        total["news"] += news_result.get("news_synced", 0)
        total["disclosures"] += disclosures_result.get("disclosures_synced", 0)

        for r in [prices_result, financials_result, news_result, disclosures_result]:
            if "error" in r:
                errors.append(f"[{stock.ticker}] {r['error']}")

    # 글로벌 동기화
    rates_result = await sync_exchange_rates(db)
    total["exchange_rates"] = rates_result.get("exchange_rates_synced", 0)
    if "error" in rates_result:
        errors.append(rates_result["error"])

    return {
        "status": "ok",
        "stocks_synced": tickers_synced,
        "global_synced": True,
        "total_synced": total,
        "errors": errors,
    }
```

- [ ] **Step 4: Register admin router in `backend/app/main.py`**

`from app.api.favorites import router as favorites_router` 아래에 추가:

```python
from app.api.admin import router as admin_router
```

`app.include_router(favorites_router)` 아래에 추가:

```python
app.include_router(admin_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_admin_api.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/admin.py backend/app/main.py backend/tests/test_admin_api.py
git commit -m "feat: add admin sync API endpoints"
```

---

### Task 9: stocks API — stats를 financials 테이블에서 조회

**Files:**
- Modify: `backend/app/api/stocks.py:7,47`
- Modify: `backend/tests/test_api.py` (해당 테스트 업데이트)

- [ ] **Step 1: Update `backend/app/api/stocks.py` stock_detail 함수**

`from app.mocks.analysis import STATS` 임포트를 제거하고, financials 테이블에서 조회하도록 변경:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Favorite, PriceHistory, Stock
from app.models.financial import Financial

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/search")
async def search(q: str = "", db: AsyncSession = Depends(get_db)):
    if not q:
        return []
    query = select(Stock).where(
        Stock.name.ilike(f"%{q}%") | Stock.ticker.ilike(f"%{q}%")
    )
    result = await db.execute(query)
    stocks = result.scalars().all()
    return [
        {
            "ticker": s.ticker,
            "name": s.name,
            "market": s.market,
            "sector": s.sector,
            "current_price": s.current_price,
            "change": s.change,
            "change_percent": s.change_percent,
        }
        for s in stocks
    ]


@router.get("/{ticker}")
async def stock_detail(ticker: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    fav_result = await db.execute(
        select(Favorite).where(Favorite.stock_id == stock.id)
    )
    is_fav = fav_result.scalar_one_or_none() is not None

    # financials 테이블에서 최신 재무지표 조회
    fin_result = await db.execute(
        select(Financial)
        .where(Financial.stock_id == stock.id)
        .order_by(Financial.created_at.desc())
        .limit(1)
    )
    fin = fin_result.scalar_one_or_none()

    stats = None
    if fin:
        stats = {
            "market_cap": f"{fin.market_cap:,}" if fin.market_cap else "N/A",
            "per": round(fin.per, 1) if fin.per else 0,
            "pbr": round(fin.pbr, 1) if fin.pbr else 0,
            "dividend_yield": round(fin.dividend_yield, 1) if fin.dividend_yield else 0,
            "high_52w": 0,  # 주가 데이터에서 계산 필요
            "low_52w": 0,
        }
        # 52주 최고/최저를 price_history에서 계산
        from sqlalchemy import func as sql_func
        from datetime import date, timedelta
        year_ago = date.today() - timedelta(days=365)
        hl_result = await db.execute(
            select(
                sql_func.max(PriceHistory.high),
                sql_func.min(PriceHistory.low),
            ).where(
                PriceHistory.stock_id == stock.id,
                PriceHistory.date >= year_ago,
            )
        )
        high_52w, low_52w = hl_result.one()
        stats["high_52w"] = high_52w or 0
        stats["low_52w"] = low_52w or 0

    return {
        "ticker": stock.ticker,
        "name": stock.name,
        "market": stock.market,
        "sector": stock.sector,
        "current_price": stock.current_price,
        "change": stock.change,
        "change_percent": stock.change_percent,
        "is_favorite": is_fav,
        "stats": stats,
    }


@router.get("/{ticker}/prices")
async def stock_prices(ticker: str, days: int = 30, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    prices_result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.stock_id == stock.id)
        .order_by(PriceHistory.date.desc())
        .limit(days)
    )
    prices = prices_result.scalars().all()

    return [
        {
            "date": p.date.isoformat(),
            "open": p.open,
            "high": p.high,
            "low": p.low,
            "close": p.close,
            "volume": p.volume,
        }
        for p in reversed(prices)
    ]
```

- [ ] **Step 2: Run existing tests to verify no regressions**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_api.py -v`
Expected: ALL PASS (stats가 None으로 반환되므로 기존 테스트 통과)

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/stocks.py
git commit -m "feat: replace mock STATS with financials table lookup"
```

---

### Task 10: 프론트엔드 — 동기화 API 함수 + 동기화 버튼

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/components/stock/stock-header.tsx`
- Modify: `frontend/src/components/layout/top-nav.tsx`

- [ ] **Step 1: Add sync API functions to `frontend/src/services/api.ts`**

파일 끝에 추가:

```typescript
export interface SyncResult {
  status: string;
  ticker?: string;
  synced: Record<string, number>;
  errors: string[];
}

export interface SyncAllResult {
  status: string;
  stocks_synced: string[];
  global_synced: boolean;
  total_synced: Record<string, number>;
  errors: string[];
}

export async function syncStock(ticker: string): Promise<SyncResult> {
  const res = await fetch(`${API_BASE}/api/admin/sync/stock/${ticker}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Sync failed: ${res.status}`);
  return res.json();
}

export async function syncAll(): Promise<SyncAllResult> {
  const res = await fetch(`${API_BASE}/api/admin/sync/all`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Sync failed: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Add sync button to `frontend/src/components/stock/stock-header.tsx`**

```tsx
"use client";

import type { Stock } from "@/types/stock";
import { addFavorite, removeFavorite, syncStock } from "@/services/api";
import { useState } from "react";

interface Props {
  stock: Stock;
  onSyncComplete?: () => void;
}

export function StockHeader({ stock, onSyncComplete }: Props) {
  const [isFav, setIsFav] = useState(stock.is_favorite ?? false);
  const [syncing, setSyncing] = useState(false);

  const toggleFavorite = async () => {
    if (isFav) {
      await removeFavorite(stock.ticker);
    } else {
      await addFavorite(stock.ticker);
    }
    setIsFav(!isFav);
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const result = await syncStock(stock.ticker);
      const { synced, errors } = result;
      const summary = Object.entries(synced)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => `${k} ${v}건`)
        .join(", ");
      alert(
        `동기화 완료: ${summary || "변경 없음"}${
          errors.length > 0 ? `\n⚠️ ${errors.join("\n")}` : ""
        }`
      );
      onSyncComplete?.();
    } catch (e) {
      alert("동기화 실패");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="flex items-center justify-between border-b border-slate-800 bg-slate-900 px-6 py-4">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-bold text-slate-50">{stock.name}</h1>
        <span className="text-sm text-slate-500">
          {stock.ticker} | {stock.market}
        </span>
        <button
          onClick={toggleFavorite}
          className="text-lg transition-transform hover:scale-110"
        >
          {isFav ? "⭐" : "☆"}
        </button>
        <button
          onClick={handleSync}
          disabled={syncing}
          className="ml-2 rounded-md border border-slate-700 bg-slate-800 px-3 py-1 text-xs text-slate-300 transition-colors hover:bg-slate-700 disabled:opacity-50"
        >
          {syncing ? "동기화 중..." : "동기화"}
        </button>
      </div>
      <div className="text-right">
        <div className="text-2xl font-bold text-slate-50">
          {stock.current_price.toLocaleString()}
          {stock.market === "KRX" ? "원" : "$"}
        </div>
        <div
          className={`text-sm font-medium ${
            stock.change_percent >= 0 ? "text-green-400" : "text-red-400"
          }`}
        >
          {stock.change_percent >= 0 ? "▲" : "▼"}{" "}
          {Math.abs(stock.change).toLocaleString()} (
          {stock.change_percent >= 0 ? "+" : ""}
          {stock.change_percent}%)
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add sync all button to `frontend/src/components/layout/top-nav.tsx`**

```tsx
"use client";

import Link from "next/link";
import { useState } from "react";
import { StockSearch } from "@/components/search/stock-search";
import { syncAll } from "@/services/api";

export function TopNav() {
  const [syncing, setSyncing] = useState(false);

  const handleSyncAll = async () => {
    setSyncing(true);
    try {
      const result = await syncAll();
      const { stocks_synced, total_synced, errors } = result;
      const summary = Object.entries(total_synced)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => `${k} ${v}건`)
        .join(", ");
      alert(
        `전체 동기화 완료 (${stocks_synced.length}개 종목)\n${summary || "변경 없음"}${
          errors.length > 0 ? `\n⚠️ ${errors.join("\n")}` : ""
        }`
      );
    } catch (e) {
      alert("전체 동기화 실패");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <nav className="flex items-center justify-between border-b border-slate-800 bg-slate-950 px-6 py-3">
      <div className="flex items-center gap-4">
        <Link href="/" className="text-lg font-bold text-slate-50">
          📊 StockInsight
        </Link>
        <StockSearch />
      </div>
      <div className="flex items-center gap-4">
        <button
          onClick={handleSyncAll}
          disabled={syncing}
          className="rounded-md border border-slate-700 bg-slate-800 px-3 py-1 text-sm text-slate-300 transition-colors hover:bg-slate-700 disabled:opacity-50"
        >
          {syncing ? "동기화 중..." : "전체 동기화"}
        </button>
        <Link
          href="/"
          className="text-sm text-yellow-400 hover:text-yellow-300 transition-colors"
        >
          ⭐ 즐겨찾기
        </Link>
      </div>
    </nav>
  );
}
```

- [ ] **Step 4: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: 빌드 성공

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/api.ts frontend/src/components/stock/stock-header.tsx frontend/src/components/layout/top-nav.tsx
git commit -m "feat: add sync buttons to stock header and top nav"
```

---

### Task 11: 뉴스/공시/환율 조회 API + 전체 테스트

**Files:**
- Create: 뉴스/공시/환율 조회 엔드포인트를 기존 라우터에 추가
- Modify: `backend/app/api/stocks.py`
- Create: `backend/app/api/exchange_rates.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add news and disclosures endpoints to `backend/app/api/stocks.py`**

파일 끝에 추가:

```python
@router.get("/{ticker}/news")
async def stock_news(ticker: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    from app.models.news import News
    news_result = await db.execute(
        select(News)
        .where(News.stock_id == stock.id)
        .order_by(News.published_at.desc())
        .limit(limit)
    )
    news_list = news_result.scalars().all()

    return [
        {
            "title": n.title,
            "source": n.source,
            "url": n.url,
            "published_at": n.published_at.isoformat(),
        }
        for n in news_list
    ]


@router.get("/{ticker}/disclosures")
async def stock_disclosures(ticker: str, limit: int = 30, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    from app.models.disclosure import Disclosure
    disc_result = await db.execute(
        select(Disclosure)
        .where(Disclosure.stock_id == stock.id)
        .order_by(Disclosure.disclosed_at.desc())
        .limit(limit)
    )
    disc_list = disc_result.scalars().all()

    return [
        {
            "title": d.title,
            "disclosure_type": d.disclosure_type,
            "disclosed_at": d.disclosed_at.isoformat(),
        }
        for d in disc_list
    ]
```

- [ ] **Step 2: Create `backend/app/api/exchange_rates.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.exchange_rate import ExchangeRate

router = APIRouter(prefix="/api/exchange-rates", tags=["exchange-rates"])


@router.get("/latest")
async def latest_rates(db: AsyncSession = Depends(get_db)):
    # 가장 최근 날짜의 환율 조회
    from sqlalchemy import func as sql_func
    max_date_result = await db.execute(select(sql_func.max(ExchangeRate.date)))
    max_date = max_date_result.scalar()
    if not max_date:
        return []

    result = await db.execute(
        select(ExchangeRate).where(ExchangeRate.date == max_date)
    )
    rates = result.scalars().all()

    return [
        {
            "date": r.date.isoformat(),
            "currency_pair": r.currency_pair,
            "rate": r.rate,
        }
        for r in rates
    ]
```

- [ ] **Step 3: Register exchange_rates router in `backend/app/main.py`**

admin_router import 아래에:

```python
from app.api.exchange_rates import router as exchange_rates_router
```

`app.include_router(admin_router)` 아래에:

```python
app.include_router(exchange_rates_router)
```

- [ ] **Step 4: Run full test suite**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/stocks.py backend/app/api/exchange_rates.py backend/app/main.py
git commit -m "feat: add news, disclosures, exchange rates read endpoints"
```

---

### Task 12: End-to-end 수동 검증 + 최종 정리

**Files:**
- Modify: `backend/app/main.py` (version bump to 0.3.0)

- [ ] **Step 1: Bump version**

`backend/app/main.py`에서 version을 `"0.3.0"`으로 변경.

- [ ] **Step 2: Run all backend tests**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 3: Start backend and test sync endpoint manually**

Run: `cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000`

별도 터미널에서:

```bash
# 환율 동기화 (API 키 불필요)
curl -X POST 'http://localhost:8000/api/admin/sync/global'

# 환율 확인
curl 'http://localhost:8000/api/exchange-rates/latest'
```

Expected: 환율 데이터가 반환됨

- [ ] **Step 4: Verify frontend builds and sync buttons render**

Run: `cd frontend && npm run build && npm run dev`

Expected: 빌드 성공, 상단에 "전체 동기화" 버튼 표시

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: bump version to 0.3.0 for Phase 1 data integration"
```
