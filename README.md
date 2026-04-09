# StockInsight

주식 분석 대시보드 -- 종목별 차트, 키워드 분석, 뉴스/공시, 재무지표를 한눈에.

## Tech Stack

| Layer | Stack |
|-------|-------|
| Frontend | Next.js 15, React 19, Tailwind CSS, shadcn/ui, lightweight-charts v5 |
| Backend | FastAPI, SQLAlchemy (async), Alembic |
| Database | PostgreSQL 16 (asyncpg) |
| Data Sources | yfinance (US), FinanceDataReader (KR), Naver News, DART, ExchangeRate API |
| Infra | Docker Compose |

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Python 3.12+
- Node.js 20+

### 1. Start Database

```bash
docker-compose up -d
```

### 2. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

### Environment Variables

**backend/.env**
```
DATABASE_URL=postgresql+asyncpg://postgres:admin123!@localhost:5432/stockinsight
DART_API_KEY=
NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
```

**frontend/.env.local**
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Scripts

```bash
./scripts/dev-all.sh        # Start backend + frontend together
./scripts/dev-backend.sh    # Start backend only
./scripts/dev-frontend.sh   # Start frontend only
./scripts/test.sh           # Run tests with coverage
./scripts/test.sh -k sync   # Run filtered tests
```

## API Endpoints

### Stocks
- `GET /api/stocks/search?q=` -- Search stocks
- `GET /api/stocks/{ticker}` -- Stock detail with financials
- `GET /api/stocks/{ticker}/prices?days=N` -- Price history (auto-fetches if missing)
- `GET /api/stocks/{ticker}/analysis?period=` -- Keyword analysis
- `GET /api/stocks/{ticker}/news` -- News
- `GET /api/stocks/{ticker}/disclosures` -- Disclosures

### Favorites
- `GET /api/favorites` -- List
- `POST /api/favorites/{ticker}` -- Add
- `DELETE /api/favorites/{ticker}` -- Remove

### Exchange Rates
- `GET /api/exchange-rates/latest` -- Latest rates

### Admin (Sync)
- `POST /api/admin/sync/stock/{ticker}` -- Sync single stock
- `POST /api/admin/sync/global` -- Sync exchange rates
- `POST /api/admin/sync/all` -- Sync all favorites + rates

## Testing

```bash
cd backend
source venv/bin/activate
python -m pytest tests/ -v --cov=app
```

69 tests, 98.5% coverage.

## Project Structure

```
cw-cy-stock/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routers
│   │   ├── collectors/     # External data collectors
│   │   ├── models/         # SQLAlchemy ORM models
│   │   ├── config.py       # Settings (pydantic-settings)
│   │   ├── database.py     # Engine + session factory
│   │   └── main.py         # App entrypoint
│   ├── alembic/            # DB migrations
│   ├── scripts/seed.py     # Seed data
│   └── tests/              # pytest
├── frontend/
│   └── src/
│       ├── app/            # Next.js pages
│       ├── components/     # UI components
│       ├── services/       # API client
│       └── types/          # TypeScript types
├── scripts/                # Dev/test shell scripts
└── docker-compose.yml      # PostgreSQL + full stack
```

## License

Private
