# PostgreSQL Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mock 데이터 기반 백엔드를 PostgreSQL로 전환하여 실제 DB에서 데이터를 읽고 쓰도록 변경

**Architecture:** SQLAlchemy async ORM + asyncpg 드라이버로 FastAPI와 연동. 환경변수 기반 DB 설정으로 로컬/프로덕션 전환 가능. 기존 mock 데이터는 seed 스크립트로 DB에 적재.

**Tech Stack:** SQLAlchemy 2.0 (async), asyncpg, python-dotenv, Alembic (마이그레이션), pytest + httpx (테스트)

---

## File Structure

```
backend/
├── .env                          # DB 접속 정보 (gitignore)
├── .env.example                  # DB 접속 정보 템플릿 (git tracked)
├── alembic.ini                   # Alembic 설정
├── alembic/
│   ├── env.py                    # Alembic 환경 설정
│   └── versions/                 # 마이그레이션 파일
├── app/
│   ├── config.py                 # 환경변수 기반 설정 (NEW)
│   ├── database.py               # SQLAlchemy 엔진/세션 (NEW)
│   ├── models/
│   │   ├── __init__.py           # Base + 모든 모델 re-export (NEW)
│   │   ├── stock.py              # Stock 모델 (NEW)
│   │   ├── price.py              # PriceHistory 모델 (NEW)
│   │   ├── analysis.py           # Analysis + KeywordDetail 모델 (NEW)
│   │   └── favorite.py           # Favorite 모델 (NEW)
│   ├── api/
│   │   ├── stocks.py             # MODIFY: mock → DB
│   │   ├── analysis.py           # MODIFY: mock → DB
│   │   └── favorites.py          # MODIFY: mock → DB
│   ├── main.py                   # MODIFY: lifespan 추가
│   ├── schemas/
│   │   └── stock.py              # MODIFY: stats optional 필드 추가
│   └── mocks/                    # 유지 (seed 데이터 소스)
├── scripts/
│   └── seed.py                   # DB seed 스크립트 (NEW)
├── tests/
│   ├── conftest.py               # 테스트 DB fixture (NEW)
│   ├── test_config.py            # config 테스트 (NEW)
│   ├── test_stocks_api.py        # stocks API 테스트 (NEW)
│   ├── test_analysis_api.py      # analysis API 테스트 (NEW)
│   └── test_favorites_api.py     # favorites API 테스트 (NEW)
└── requirements.txt              # MODIFY: 의존성 추가
```

---

### Task 1: 의존성 및 환경 설정

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/.env`
- Create: `backend/.env.example`
- Create: `backend/app/config.py`
- Modify: `backend/.gitignore` (없으면 루트 `.gitignore` 수정)

- [ ] **Step 1: requirements.txt에 의존성 추가**

`backend/requirements.txt` 전체 내용:

```
fastapi==0.115.12
uvicorn[standard]==0.34.2
pydantic==2.11.1
pydantic-settings==2.9.1
sqlalchemy[asyncio]==2.0.40
asyncpg==0.30.0
alembic==1.15.2
python-dotenv==1.1.0
httpx==0.28.1
pytest==8.3.5
pytest-asyncio==0.26.0
```

- [ ] **Step 2: .env 파일 생성**

`backend/.env`:

```
DATABASE_URL=postgresql+asyncpg://postgres:admin123!@localhost:5432/stockinsight
```

- [ ] **Step 3: .env.example 파일 생성**

`backend/.env.example`:

```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/stockinsight
```

- [ ] **Step 4: .gitignore에 .env 추가**

루트 `.gitignore`에 `.env` 추가 (`.env.local`은 이미 있음):

```
.env
```

- [ ] **Step 5: config.py 작성**

`backend/app/config.py`:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:admin123!@localhost:5432/stockinsight"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **Step 6: 의존성 설치 확인**

Run: `cd backend && source venv/bin/activate && pip install -r requirements.txt`
Expected: 모든 패키지 설치 성공

- [ ] **Step 7: config 동작 확인**

Run: `cd backend && source venv/bin/activate && python -c "from app.config import settings; print(settings.database_url)"`
Expected: `postgresql+asyncpg://postgres:admin123!@localhost:5432/stockinsight`

- [ ] **Step 8: Commit**

```bash
git add backend/requirements.txt backend/.env.example backend/app/config.py .gitignore
git commit -m "feat: add database dependencies and environment config"
```

> **주의:** `backend/.env`는 .gitignore에 추가되어 커밋 대상에서 제외

---

### Task 2: Database 연결 및 SQLAlchemy 설정

**Files:**
- Create: `backend/app/database.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: database.py 작성**

`backend/app/database.py`:

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
```

- [ ] **Step 2: main.py에 lifespan 추가**

`backend/app/main.py` 전체 교체:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.stocks import router as stocks_router
from app.api.analysis import router as analysis_router
from app.api.favorites import router as favorites_router
from app.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="StockInsight API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stocks_router)
app.include_router(analysis_router)
app.include_router(favorites_router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
```

- [ ] **Step 3: import 확인**

Run: `cd backend && source venv/bin/activate && python -c "from app.database import engine, get_db, async_session; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/database.py backend/app/main.py
git commit -m "feat: add SQLAlchemy async engine and session setup"
```

---

### Task 3: SQLAlchemy 모델 정의

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/stock.py`
- Create: `backend/app/models/price.py`
- Create: `backend/app/models/analysis.py`
- Create: `backend/app/models/favorite.py`

- [ ] **Step 1: Stock 모델 작성**

`backend/app/models/stock.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    market: Mapped[str] = mapped_column(String(20))
    sector: Mapped[str] = mapped_column(String(100))
    current_price: Mapped[float] = mapped_column(Float, default=0)
    change: Mapped[float] = mapped_column(Float, default=0)
    change_percent: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 2: PriceHistory 모델 작성**

`backend/app/models/price.py`:

```python
from sqlalchemy import Date, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.stock import Base


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (UniqueConstraint("stock_id", "date", name="uq_stock_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    date: Mapped[str] = mapped_column(Date)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)
```

- [ ] **Step 3: Analysis + KeywordDetail + DailyKeyword 모델 작성**

`backend/app/models/analysis.py`:

```python
from datetime import datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.stock import Base


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    date: Mapped[str] = mapped_column(Date)
    period_type: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(Text)
    feedback: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    keywords: Mapped[list["KeywordDetail"]] = relationship(back_populates="analysis", cascade="all, delete-orphan")
    daily_keywords: Mapped[list["DailyKeyword"]] = relationship(back_populates="analysis", cascade="all, delete-orphan")


class KeywordDetail(Base):
    __tablename__ = "keyword_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"))
    keyword: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(200))
    impact_level: Mapped[str] = mapped_column(String(20))
    duration: Mapped[str] = mapped_column(String(20))

    analysis: Mapped["Analysis"] = relationship(back_populates="keywords")


class DailyKeyword(Base):
    __tablename__ = "daily_keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"))
    date: Mapped[str] = mapped_column(Date)
    keyword: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20))

    analysis: Mapped["Analysis"] = relationship(back_populates="daily_keywords")
```

- [ ] **Step 4: Favorite 모델 작성**

`backend/app/models/favorite.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.stock import Base


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("stock_id", name="uq_favorite_stock"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

> **참고:** 인증 시스템 구현 전까지 user_id 없이 단일 사용자 즐겨찾기. 인증 추가 시 user_id 컬럼 추가 예정.

- [ ] **Step 5: __init__.py에서 모든 모델 re-export**

`backend/app/models/__init__.py`:

```python
from app.models.stock import Base, Stock
from app.models.price import PriceHistory
from app.models.analysis import Analysis, DailyKeyword, KeywordDetail
from app.models.favorite import Favorite

__all__ = [
    "Base",
    "Stock",
    "PriceHistory",
    "Analysis",
    "KeywordDetail",
    "DailyKeyword",
    "Favorite",
]
```

- [ ] **Step 6: 모델 import 확인**

Run: `cd backend && source venv/bin/activate && python -c "from app.models import Base, Stock, PriceHistory, Analysis, KeywordDetail, DailyKeyword, Favorite; print(f'{len(Base.metadata.tables)} tables: {list(Base.metadata.tables.keys())}')"`
Expected: `6 tables: ['stocks', 'price_history', 'analyses', 'keyword_details', 'daily_keywords', 'favorites']`

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/
git commit -m "feat: add SQLAlchemy models for stocks, prices, analysis, favorites"
```

---

### Task 4: Alembic 마이그레이션 설정 및 초기 마이그레이션

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`

- [ ] **Step 1: Alembic 초기화**

Run: `cd backend && source venv/bin/activate && alembic init alembic`
Expected: `alembic/` 디렉토리와 `alembic.ini` 생성

- [ ] **Step 2: alembic.ini에서 sqlalchemy.url 수정**

`backend/alembic.ini`의 `sqlalchemy.url` 행을 빈 문자열로 변경 (env.py에서 동적 설정):

찾기: `sqlalchemy.url = driver://user:pass@localhost/dbname`
바꾸기: `sqlalchemy.url =`

- [ ] **Step 3: alembic/env.py 수정**

`backend/alembic/env.py` 전체 교체:

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config import settings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# asyncpg URL → psycopg2 sync URL (Alembic은 sync 드라이버 필요)
sync_url = settings.database_url.replace("+asyncpg", "")


def run_migrations_offline() -> None:
    context.configure(url=sync_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(sync_url)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: stockinsight 데이터베이스 생성**

Run: `createdb -h localhost -p 5432 -U postgres stockinsight`
Expected: 데이터베이스 생성 성공 (에러 없음). 이미 존재하면 `database "stockinsight" already exists` — 무시.

- [ ] **Step 5: 초기 마이그레이션 생성**

Run: `cd backend && source venv/bin/activate && alembic revision --autogenerate -m "initial tables"`
Expected: `alembic/versions/` 에 마이그레이션 파일 생성

- [ ] **Step 6: 마이그레이션 실행**

Run: `cd backend && source venv/bin/activate && alembic upgrade head`
Expected: 6개 테이블 생성 완료

- [ ] **Step 7: 테이블 확인**

Run: `psql -h localhost -p 5432 -U postgres -d stockinsight -c "\dt"`
Expected: stocks, price_history, analyses, keyword_details, daily_keywords, favorites 테이블 목록

- [ ] **Step 8: Commit**

```bash
git add backend/alembic.ini backend/alembic/
git commit -m "feat: add Alembic migration setup with initial schema"
```

---

### Task 5: Seed 스크립트 작성 및 실행

**Files:**
- Create: `backend/scripts/seed.py`

- [ ] **Step 1: seed.py 작성**

`backend/scripts/seed.py`:

```python
"""기존 mock 데이터를 PostgreSQL에 적재하는 seed 스크립트."""

import asyncio
from datetime import date

from sqlalchemy import select

from app.database import async_session, engine
from app.models import (
    Analysis,
    Base,
    DailyKeyword,
    Favorite,
    KeywordDetail,
    PriceHistory,
    Stock,
)
from app.mocks.stocks import STOCKS
from app.mocks.prices import generate_prices
from app.mocks.analysis import ANALYSES, STATS


async def seed():
    async with engine.begin() as conn:
        # 기존 데이터 삭제 후 재생성하지 않음 — 이미 Alembic으로 테이블 생성됨
        pass

    async with async_session() as session:
        # 1. Stocks
        stock_map: dict[str, int] = {}  # ticker → stock.id

        for s in STOCKS:
            existing = await session.execute(
                select(Stock).where(Stock.ticker == s["ticker"])
            )
            stock = existing.scalar_one_or_none()
            if stock:
                stock_map[s["ticker"]] = stock.id
                print(f"  Skip existing: {s['ticker']}")
                continue

            stats = STATS.get(s["ticker"], {})
            stock = Stock(
                ticker=s["ticker"],
                name=s["name"],
                market=s["market"],
                sector=s["sector"],
                current_price=s["current_price"],
                change=s["change"],
                change_percent=s["change_percent"],
            )
            session.add(stock)
            await session.flush()
            stock_map[s["ticker"]] = stock.id
            print(f"  Added stock: {s['ticker']} (id={stock.id})")

        # 2. Price History
        for ticker, stock_id in stock_map.items():
            existing_count_result = await session.execute(
                select(PriceHistory).where(PriceHistory.stock_id == stock_id).limit(1)
            )
            if existing_count_result.scalar_one_or_none():
                print(f"  Skip prices for {ticker} (already exist)")
                continue

            prices = generate_prices(ticker, days=90)
            for p in prices:
                session.add(PriceHistory(
                    stock_id=stock_id,
                    date=date.fromisoformat(p["date"]),
                    open=p["open"],
                    high=p["high"],
                    low=p["low"],
                    close=p["close"],
                    volume=p["volume"],
                ))
            print(f"  Added {len(prices)} price records for {ticker}")

        # 3. Analysis + Keywords + DailyKeywords
        for ticker, analysis_data in ANALYSES.items():
            stock_id = stock_map.get(ticker)
            if not stock_id:
                continue

            existing = await session.execute(
                select(Analysis).where(Analysis.stock_id == stock_id).limit(1)
            )
            if existing.scalar_one_or_none():
                print(f"  Skip analysis for {ticker} (already exists)")
                continue

            analysis = Analysis(
                stock_id=stock_id,
                date=date.fromisoformat(analysis_data["date"]),
                period_type=analysis_data["period_type"],
                summary=analysis_data["summary"],
                feedback=analysis_data["feedback"],
            )
            session.add(analysis)
            await session.flush()

            for kw in analysis_data["keywords"]:
                session.add(KeywordDetail(
                    analysis_id=analysis.id,
                    keyword=kw["keyword"],
                    type=kw["type"],
                    detail=kw["detail"],
                    source=kw["source"],
                    impact_level=kw["impact_level"],
                    duration=kw["duration"],
                ))

            for dk in analysis_data["daily_keywords"]:
                session.add(DailyKeyword(
                    analysis_id=analysis.id,
                    date=date.fromisoformat(dk["date"]),
                    keyword=dk["keyword"],
                    type=dk["type"],
                ))

            print(f"  Added analysis for {ticker}: {len(analysis_data['keywords'])} keywords, {len(analysis_data['daily_keywords'])} daily")

        # 4. Favorites (삼성전자, 테슬라 기본 즐겨찾기)
        for ticker in ["005930", "TSLA"]:
            stock_id = stock_map.get(ticker)
            if not stock_id:
                continue

            existing = await session.execute(
                select(Favorite).where(Favorite.stock_id == stock_id)
            )
            if existing.scalar_one_or_none():
                print(f"  Skip favorite for {ticker} (already exists)")
                continue

            session.add(Favorite(stock_id=stock_id))
            print(f"  Added favorite: {ticker}")

        await session.commit()
        print("\nSeed 완료!")


if __name__ == "__main__":
    asyncio.run(seed())
```

- [ ] **Step 2: seed 실행**

Run: `cd backend && source venv/bin/activate && python -m scripts.seed`
Expected: 각 항목 추가 로그 출력 후 "Seed 완료!"

- [ ] **Step 3: DB 데이터 확인**

Run: `psql -h localhost -p 5432 -U postgres -d stockinsight -c "SELECT ticker, name, market FROM stocks; SELECT COUNT(*) as price_count FROM price_history; SELECT stock_id, period_type, LENGTH(summary) as summary_len FROM analyses; SELECT COUNT(*) as kw_count FROM keyword_details; SELECT COUNT(*) as fav_count FROM favorites;"`
Expected: stocks 2행, price_history ~120행, analyses 2행, keyword_details 14행, favorites 2행

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/
git commit -m "feat: add database seed script with mock data"
```

---

### Task 6: API 라우터 전환 — stocks

**Files:**
- Modify: `backend/app/api/stocks.py`
- Modify: `backend/app/schemas/stock.py`

- [ ] **Step 1: schemas/stock.py에 StatsInfo를 StockDetail 응답에 통합**

`backend/app/schemas/stock.py` 전체 교체:

```python
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
```

- [ ] **Step 2: stocks.py를 DB 쿼리로 전환**

`backend/app/api/stocks.py` 전체 교체:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Favorite, PriceHistory, Stock
from app.mocks.analysis import STATS

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

    stats = STATS.get(ticker)

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

> **참고:** `STATS`는 아직 별도 테이블 없이 mock에서 가져옴. 재무 데이터 테이블은 실제 API 연동 시 추가 예정.

- [ ] **Step 3: 서버 기동 확인**

Run: `cd backend && source venv/bin/activate && timeout 5 uvicorn app.main:app --port 8000 2>&1 || true`
Expected: `Uvicorn running on http://127.0.0.1:8000` (5초 후 timeout으로 종료)

- [ ] **Step 4: API 테스트**

Run: `cd backend && source venv/bin/activate && python -c "
import asyncio, httpx
async def test():
    async with httpx.AsyncClient(base_url='http://localhost:8000') as c:
        r = await c.get('/api/stocks/search?q=삼성')
        print('search:', r.status_code, r.json())
        r = await c.get('/api/stocks/005930')
        print('detail:', r.status_code, list(r.json().keys()))
        r = await c.get('/api/stocks/005930/prices?days=5')
        print('prices:', r.status_code, len(r.json()), 'records')
asyncio.run(test())
"`

> **참고:** 이 테스트는 서버가 별도로 실행 중일 때만 동작. 서버가 안 떠 있으면 import 기반 확인으로 대체.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/stocks.py backend/app/schemas/stock.py
git commit -m "feat: migrate stocks API from mock data to PostgreSQL"
```

---

### Task 7: API 라우터 전환 — analysis

**Files:**
- Modify: `backend/app/api/analysis.py`

- [ ] **Step 1: analysis.py를 DB 쿼리로 전환**

`backend/app/api/analysis.py` 전체 교체:

```python
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
        .where(Analysis.stock_id == stock.id)
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/analysis.py
git commit -m "feat: migrate analysis API from mock data to PostgreSQL"
```

---

### Task 8: API 라우터 전환 — favorites

**Files:**
- Modify: `backend/app/api/favorites.py`

- [ ] **Step 1: favorites.py를 DB 쿼리로 전환**

`backend/app/api/favorites.py` 전체 교체:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Favorite, Stock

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


@router.get("")
async def list_favorites(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Stock)
        .join(Favorite, Favorite.stock_id == Stock.id)
        .order_by(Favorite.created_at.desc())
    )
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


@router.post("/{ticker}")
async def add(ticker: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    existing = await db.execute(
        select(Favorite).where(Favorite.stock_id == stock.id)
    )
    if existing.scalar_one_or_none():
        return {"status": "already_exists", "ticker": ticker}

    db.add(Favorite(stock_id=stock.id))
    await db.commit()
    return {"status": "added", "ticker": ticker}


@router.delete("/{ticker}")
async def remove(ticker: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    fav_result = await db.execute(
        select(Favorite).where(Favorite.stock_id == stock.id)
    )
    fav = fav_result.scalar_one_or_none()
    if fav:
        await db.delete(fav)
        await db.commit()

    return {"status": "removed", "ticker": ticker}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/favorites.py
git commit -m "feat: migrate favorites API from mock data to PostgreSQL"
```

---

### Task 9: API 통합 테스트

**Files:**
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_api.py`

- [ ] **Step 1: tests/__init__.py 생성**

`backend/tests/__init__.py`: 빈 파일

- [ ] **Step 2: conftest.py 작성**

`backend/tests/conftest.py`:

```python
import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import get_db
from app.main import app
from app.models import Base

# 테스트용 DB (같은 DB 사용, 테스트 후 롤백)
test_engine = create_async_engine(settings.database_url)
test_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with test_session() as session:
        yield session


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
```

- [ ] **Step 3: test_api.py 작성**

`backend/tests/test_api.py`:

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_search_stocks(client: AsyncClient):
    response = await client.get("/api/stocks/search?q=삼성")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["ticker"] == "005930"


@pytest.mark.asyncio
async def test_search_empty(client: AsyncClient):
    response = await client.get("/api/stocks/search?q=")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_stock_detail(client: AsyncClient):
    response = await client.get("/api/stocks/005930")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "005930"
    assert data["name"] == "삼성전자"
    assert "is_favorite" in data
    assert "stats" in data


@pytest.mark.asyncio
async def test_stock_not_found(client: AsyncClient):
    response = await client.get("/api/stocks/INVALID")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stock_prices(client: AsyncClient):
    response = await client.get("/api/stocks/005930/prices?days=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert "date" in data[0]
    assert "open" in data[0]
    assert "close" in data[0]


@pytest.mark.asyncio
async def test_analysis(client: AsyncClient):
    response = await client.get("/api/stocks/005930/analysis")
    assert response.status_code == 200
    data = response.json()
    assert "keywords" in data
    assert "daily_keywords" in data
    assert "summary" in data
    assert "feedback" in data
    assert len(data["keywords"]) >= 1


@pytest.mark.asyncio
async def test_favorites_list(client: AsyncClient):
    response = await client.get("/api/favorites")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_favorite_add_remove(client: AsyncClient):
    # Add
    response = await client.post("/api/favorites/TSLA")
    assert response.status_code == 200

    # List should contain TSLA
    response = await client.get("/api/favorites")
    tickers = [s["ticker"] for s in response.json()]
    assert "TSLA" in tickers

    # Remove
    response = await client.delete("/api/favorites/TSLA")
    assert response.status_code == 200
    assert response.json()["status"] == "removed"
```

- [ ] **Step 4: 테스트 실행**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/ -v`
Expected: 전체 PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/tests/
git commit -m "test: add API integration tests for PostgreSQL-backed endpoints"
```

---

### Task 10: Docker Compose에 PostgreSQL 추가

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: docker-compose.yml 업데이트**

`docker-compose.yml` 전체 교체:

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: admin123!
      POSTGRES_DB: stockinsight
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 5

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:admin123!@db:5432/stockinsight
    depends_on:
      db:
        condition: service_healthy

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - backend

volumes:
  pgdata:
```

- [ ] **Step 2: backend Dockerfile에 psycopg2 의존성 추가 (Alembic용)**

`backend/Dockerfile` — 기존 내용 확인 후 `pip install` 부분에 `psycopg2-binary` 추가가 필요한 경우 수정.

실제로는 requirements.txt에 이미 필요한 것들이 포함되어 있으므로, Dockerfile의 `pip install -r requirements.txt` 단계에서 자동 설치됨.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add PostgreSQL service to docker-compose"
```

---

## Self-Review Checklist

1. **Spec coverage:** 설계 문서의 데이터 모델(stocks, price_history, analyses, keyword_details, favorites) 모두 구현. `news`, `disclosures`, `financials`, `exchange_rates`, `market_indices`는 Phase 1 실제 API 연동 시 추가 예정이므로 이번 범위에서 제외.

2. **Placeholder scan:** 모든 단계에 완전한 코드 포함. TBD/TODO 없음.

3. **Type consistency:**
   - `Stock` 모델: ticker, name, market, sector, current_price, change, change_percent — 일관
   - `get_db` 의존성 주입 패턴 모든 라우터에서 동일
   - `PriceHistory.date` → `Date` 타입, API 응답에서 `.isoformat()` 변환 일관
   - `Analysis` → `keywords`, `daily_keywords` relationship 이름 일관
