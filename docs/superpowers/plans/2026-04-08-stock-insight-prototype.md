# StockInsight 프로토타입 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 목업 데이터 기반으로 주식 분석 대시보드 프로토타입을 구현한다. 실제 API/DB/LLM 연동 없이 UI와 데이터 흐름을 검증한다.

**Architecture:** Next.js 프론트엔드(목업 데이터) + FastAPI 백엔드(목업 JSON 응답). 프론트엔드가 백엔드 API를 호출하고, 백엔드는 하드코딩된 목업 데이터를 반환한다. DB 없이 인메모리/JSON 파일로 동작.

**Tech Stack:** Next.js 15 (App Router), React, TypeScript, shadcn/ui, Tailwind CSS, Lightweight Charts (TradingView), FastAPI, Python, uvicorn

**Spec:** `docs/superpowers/specs/2026-04-08-stock-insight-design.md`

---

## File Structure

### Frontend (`frontend/`)

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx              # 루트 레이아웃 (다크 테마, 폰트)
│   │   ├── page.tsx                # 메인 페이지 (즐겨찾기 목록 + 검색)
│   │   └── stock/[ticker]/
│   │       └── page.tsx            # 종목 대시보드 페이지
│   ├── components/
│   │   ├── ui/                     # shadcn/ui 공통 컴포넌트 (자동 생성)
│   │   ├── layout/
│   │   │   └── top-nav.tsx         # 상단 네비게이션 (검색 + 즐겨찾기)
│   │   ├── stock/
│   │   │   ├── stock-header.tsx    # 종목 헤더 (이름, 현재가, 등락률, ⭐)
│   │   │   ├── period-tabs.tsx     # 기간 탭 (일간~연간)
│   │   │   ├── price-chart.tsx     # 캔들+라인 차트 (Lightweight Charts)
│   │   │   ├── chart-toggles.tsx   # 차트 오버레이 토글 (종가/MA)
│   │   │   ├── keyword-timeline.tsx # 차트 아래 날짜별 키워드 타임라인
│   │   │   ├── keyword-section.tsx # 상승/하락/보합 키워드 영역
│   │   │   ├── keyword-tag.tsx     # 개별 키워드 태그
│   │   │   ├── detail-panel.tsx    # 오른쪽 상세 리포트 패널
│   │   │   ├── ai-feedback.tsx     # AI 피드백 & 대책 카드
│   │   │   └── stats-card.tsx      # 주요 지표 카드
│   │   └── search/
│   │       └── stock-search.tsx    # ⌘K 종목 검색 (Command Palette)
│   ├── services/
│   │   └── api.ts                  # 백엔드 API 호출 함수
│   ├── types/
│   │   └── stock.ts                # TypeScript 타입 정의
│   └── lib/
│       └── utils.ts                # shadcn/ui 유틸리티
├── package.json
├── tailwind.config.ts
├── tsconfig.json
├── next.config.ts
└── components.json                 # shadcn/ui 설정
```

### Backend (`backend/`)

```
backend/
├── app/
│   ├── main.py                     # FastAPI 앱 엔트리포인트
│   ├── api/
│   │   ├── stocks.py               # 종목 관련 엔드포인트
│   │   ├── analysis.py             # 분석 관련 엔드포인트
│   │   └── favorites.py            # 즐겨찾기 엔드포인트
│   ├── schemas/
│   │   └── stock.py                # Pydantic 응답 스키마
│   └── mocks/
│       ├── stocks.py               # 종목 마스터 목업
│       ├── prices.py               # 주가 히스토리 목업
│       ├── analysis.py             # 분석 결과 목업 (키워드 포함)
│       └── favorites.py            # 즐겨찾기 목업 (인메모리)
├── requirements.txt
└── Dockerfile
```

---

## Task 1: 프로젝트 초기화 — 프론트엔드

**Files:**
- Create: `frontend/package.json`, `frontend/tailwind.config.ts`, `frontend/tsconfig.json`, `frontend/next.config.ts`, `frontend/components.json`
- Create: `frontend/src/app/layout.tsx`, `frontend/src/app/page.tsx`
- Create: `frontend/src/lib/utils.ts`

- [ ] **Step 1: Next.js 프로젝트 생성**

```bash
cd /Users/cwkim/Documents/workspace/cw-cy-stock
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm
```

프롬프트 응답:
- Would you like to use Turbopack? → Yes

- [ ] **Step 2: shadcn/ui 초기화**

```bash
cd frontend
npx shadcn@latest init
```

프롬프트 응답:
- Style: Default
- Base color: Slate
- CSS variables: Yes

- [ ] **Step 3: 필요한 shadcn/ui 컴포넌트 설치**

```bash
cd frontend
npx shadcn@latest add button badge tabs toggle tooltip command dialog
```

- [ ] **Step 4: 루트 레이아웃에 다크 테마 적용**

`frontend/src/app/layout.tsx`를 수정 — `<html>` 태그에 `className="dark"` 추가:

```tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "StockInsight — 주식 분석 대시보드",
  description: "주식 종목의 상승/하락/보합 요인을 확인하고 AI 피드백을 받는 서비스",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" className="dark">
      <body className={`${inter.className} bg-slate-950 text-slate-50 min-h-screen`}>
        {children}
      </body>
    </html>
  );
}
```

- [ ] **Step 5: 메인 페이지 placeholder 작성**

`frontend/src/app/page.tsx`:

```tsx
export default function Home() {
  return (
    <div className="flex items-center justify-center min-h-screen">
      <h1 className="text-2xl font-bold">StockInsight</h1>
    </div>
  );
}
```

- [ ] **Step 6: 개발 서버 실행 확인**

```bash
cd frontend
npm run dev
```

브라우저에서 `http://localhost:3000` 접속, "StockInsight" 텍스트가 다크 배경에 보이는지 확인.

- [ ] **Step 7: 커밋**

```bash
cd /Users/cwkim/Documents/workspace/cw-cy-stock
git add frontend/
git commit -m "feat: initialize Next.js frontend with shadcn/ui and dark theme"
```

---

## Task 2: 프로젝트 초기화 — 백엔드

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/main.py`

- [ ] **Step 1: 백엔드 디렉토리 생성**

```bash
cd /Users/cwkim/Documents/workspace/cw-cy-stock
mkdir -p backend/app/api backend/app/schemas backend/app/mocks
touch backend/app/__init__.py backend/app/api/__init__.py backend/app/schemas/__init__.py backend/app/mocks/__init__.py
```

- [ ] **Step 2: requirements.txt 작성**

`backend/requirements.txt`:

```
fastapi==0.115.12
uvicorn[standard]==0.34.2
pydantic==2.11.1
```

- [ ] **Step 3: Python 가상환경 생성 및 의존성 설치**

```bash
cd /Users/cwkim/Documents/workspace/cw-cy-stock/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 4: FastAPI 엔트리포인트 작성**

`backend/app/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="StockInsight API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
```

- [ ] **Step 5: 서버 실행 확인**

```bash
cd /Users/cwkim/Documents/workspace/cw-cy-stock/backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

브라우저에서 `http://localhost:8000/api/health` 접속, `{"status":"ok"}` 확인.

- [ ] **Step 6: .gitignore 업데이트 후 커밋**

`.gitignore`에 추가:

```
backend/venv/
__pycache__/
*.pyc
```

```bash
cd /Users/cwkim/Documents/workspace/cw-cy-stock
git add backend/ .gitignore
git commit -m "feat: initialize FastAPI backend with health check endpoint"
```

---

## Task 3: 백엔드 목업 데이터 및 API

**Files:**
- Create: `backend/app/schemas/stock.py`
- Create: `backend/app/mocks/stocks.py`
- Create: `backend/app/mocks/prices.py`
- Create: `backend/app/mocks/analysis.py`
- Create: `backend/app/mocks/favorites.py`
- Create: `backend/app/api/stocks.py`
- Create: `backend/app/api/analysis.py`
- Create: `backend/app/api/favorites.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Pydantic 스키마 정의**

`backend/app/schemas/stock.py`:

```python
from pydantic import BaseModel


class Stock(BaseModel):
    ticker: str
    name: str
    market: str  # KRX, NYSE, NASDAQ
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
    type: str  # bullish, bearish, neutral
    detail: str
    source: str
    impact_level: str  # high, mid, low
    duration: str  # short, mid, long


class DailyKeyword(BaseModel):
    date: str
    keyword: str
    type: str  # bullish, bearish, neutral


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
```

- [ ] **Step 2: 종목 마스터 목업**

`backend/app/mocks/stocks.py`:

```python
STOCKS = [
    {
        "ticker": "005930",
        "name": "삼성전자",
        "market": "KRX",
        "sector": "반도체",
        "current_price": 71500,
        "change": -1200,
        "change_percent": -1.65,
    },
    {
        "ticker": "000660",
        "name": "SK하이닉스",
        "market": "KRX",
        "sector": "반도체",
        "current_price": 178000,
        "change": 3500,
        "change_percent": 2.01,
    },
    {
        "ticker": "AAPL",
        "name": "Apple",
        "market": "NASDAQ",
        "sector": "Technology",
        "current_price": 195.42,
        "change": 2.15,
        "change_percent": 1.11,
    },
    {
        "ticker": "NVDA",
        "name": "NVIDIA",
        "market": "NASDAQ",
        "sector": "Semiconductors",
        "current_price": 824.18,
        "change": -12.30,
        "change_percent": -1.47,
    },
    {
        "ticker": "035720",
        "name": "카카오",
        "market": "KRX",
        "sector": "인터넷",
        "current_price": 42150,
        "change": 650,
        "change_percent": 1.57,
    },
]


def search_stocks(query: str) -> list[dict]:
    q = query.lower()
    return [s for s in STOCKS if q in s["name"].lower() or q in s["ticker"].lower()]


def get_stock(ticker: str) -> dict | None:
    for s in STOCKS:
        if s["ticker"] == ticker:
            return s
    return None
```

- [ ] **Step 3: 주가 히스토리 목업**

`backend/app/mocks/prices.py`:

```python
import random
from datetime import datetime, timedelta


def generate_prices(ticker: str, days: int = 30) -> list[dict]:
    """지정 일수만큼의 가짜 일봉 데이터를 생성한다."""
    base_prices = {
        "005930": 71500,
        "000660": 178000,
        "AAPL": 195.42,
        "NVDA": 824.18,
        "035720": 42150,
    }
    base = base_prices.get(ticker, 100)
    prices = []
    current = base * 0.95
    today = datetime(2026, 4, 8)

    for i in range(days, 0, -1):
        date = today - timedelta(days=i)
        if date.weekday() >= 5:  # 주말 제외
            continue
        change_pct = random.uniform(-0.03, 0.03)
        open_price = round(current, 2)
        close_price = round(current * (1 + change_pct), 2)
        high_price = round(max(open_price, close_price) * (1 + random.uniform(0, 0.015)), 2)
        low_price = round(min(open_price, close_price) * (1 - random.uniform(0, 0.015)), 2)
        volume = random.randint(5000000, 30000000)

        prices.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": volume,
        })
        current = close_price

    return prices
```

- [ ] **Step 4: 분석 결과 목업**

`backend/app/mocks/analysis.py`:

```python
ANALYSES = {
    "005930": {
        "date": "2026-04-08",
        "period_type": "weekly",
        "keywords": [
            {
                "keyword": "HBM 수주 확대",
                "type": "bullish",
                "detail": "삼성전자가 엔비디아 차세대 GPU용 HBM3E 공급 계약을 체결했다는 보도가 나왔습니다. 이에 따라 2026년 하반기 HBM 매출이 전년 대비 40% 이상 증가할 것으로 전망됩니다.",
                "source": "한국경제 (2026.04.05)",
                "impact_level": "high",
                "duration": "mid",
            },
            {
                "keyword": "AI 반도체 수요 증가",
                "type": "bullish",
                "detail": "글로벌 AI 투자 확대로 데이터센터향 반도체 수요가 급증하고 있습니다. 삼성전자의 서버용 DRAM 출하량이 전분기 대비 25% 증가했습니다.",
                "source": "매일경제 (2026.04.03)",
                "impact_level": "high",
                "duration": "long",
            },
            {
                "keyword": "외국인 순매수",
                "type": "bullish",
                "detail": "외국인 투자자들이 이번 주 삼성전자를 3거래일 연속 순매수했습니다. 누적 순매수 금액은 약 2,800억원입니다.",
                "source": "KRX 투자자별 매매동향",
                "impact_level": "mid",
                "duration": "short",
            },
            {
                "keyword": "미중 무역갈등",
                "type": "bearish",
                "detail": "미국이 중국에 대한 반도체 수출 규제를 추가 강화할 가능성이 보도되었습니다. 삼성전자의 중국 시안 NAND 공장 운영에 영향을 미칠 수 있습니다.",
                "source": "Reuters (2026.04.06)",
                "impact_level": "high",
                "duration": "mid",
            },
            {
                "keyword": "원/달러 환율 상승",
                "type": "bearish",
                "detail": "원/달러 환율이 1,380원을 돌파하며 수출 기업의 환차익이 감소했습니다. 외국인 투자자의 환헤지 비용 부담도 증가합니다.",
                "source": "한국은행 (2026.04.07)",
                "impact_level": "mid",
                "duration": "short",
            },
            {
                "keyword": "메모리 가격 하락세",
                "type": "bearish",
                "detail": "범용 DRAM 고정거래가격이 전월 대비 5% 하락했습니다. 재고 조정 국면이 이어지고 있으나 HBM 수요가 이를 상쇄할 전망입니다.",
                "source": "DRAMeXchange (2026.04.04)",
                "impact_level": "mid",
                "duration": "mid",
            },
            {
                "keyword": "실적 컨센서스 부합",
                "type": "neutral",
                "detail": "증권사 컨센서스 기준 2026년 1분기 영업이익은 약 9.2조원으로 시장 기대치에 부합하는 수준입니다.",
                "source": "FnGuide 컨센서스",
                "impact_level": "low",
                "duration": "short",
            },
            {
                "keyword": "배당 정책 유지",
                "type": "neutral",
                "detail": "삼성전자는 기존 주주환원 정책을 유지하겠다고 밝혔습니다. 연간 배당수익률 약 2.1% 수준이 예상됩니다.",
                "source": "삼성전자 IR (2026.03)",
                "impact_level": "low",
                "duration": "long",
            },
        ],
        "daily_keywords": [
            {"date": "2026-04-01", "keyword": "실적 호조 전망", "type": "bullish"},
            {"date": "2026-04-02", "keyword": "HBM 수주 보도", "type": "bullish"},
            {"date": "2026-04-03", "keyword": "관세 리스크 부각", "type": "bearish"},
            {"date": "2026-04-04", "keyword": "외국인 반등 매수", "type": "bullish"},
            {"date": "2026-04-07", "keyword": "환율 급등 부담", "type": "bearish"},
        ],
        "summary": "주간 기준 삼성전자는 HBM 수주 확대와 AI 반도체 수요 모멘텀에도 불구하고, 미중 무역갈등과 환율 부담으로 혼조세를 보이고 있습니다. 상승 요인과 하락 요인이 균형을 이루며 주가는 71,000~73,000원 박스권에서 등락하고 있습니다.",
        "feedback": "중장기 투자자라면 메모리 가격 반등 시점을 주시하며, 현 구간에서는 분할 매수 전략이 유효할 수 있습니다. HBM 매출 비중 확대가 확인되는 시점이 본격적인 상승 전환의 트리거가 될 전망입니다. 환율 리스크는 단기적이므로 과도한 비중 축소보다는 보유 관점이 적절합니다.",
    },
    "000660": {
        "date": "2026-04-08",
        "period_type": "weekly",
        "keywords": [
            {
                "keyword": "HBM 시장 점유율 1위",
                "type": "bullish",
                "detail": "SK하이닉스가 HBM 글로벌 시장 점유율 50% 이상을 유지하고 있으며, 엔비디아 H200 및 B100향 독점 공급이 계속되고 있습니다.",
                "source": "TrendForce (2026.04.02)",
                "impact_level": "high",
                "duration": "long",
            },
            {
                "keyword": "실적 어닝 서프라이즈",
                "type": "bullish",
                "detail": "2026년 1분기 영업이익이 시장 예상치를 15% 상회할 것으로 전망됩니다. HBM과 서버용 DDR5 매출이 실적을 견인하고 있습니다.",
                "source": "증권사 리포트 종합",
                "impact_level": "high",
                "duration": "mid",
            },
            {
                "keyword": "글로벌 경기 둔화 우려",
                "type": "bearish",
                "detail": "IMF가 2026년 글로벌 성장률 전망치를 하향 조정하면서 반도체 업종 전반에 대한 우려가 부각되었습니다.",
                "source": "IMF World Economic Outlook (2026.04)",
                "impact_level": "mid",
                "duration": "mid",
            },
        ],
        "daily_keywords": [
            {"date": "2026-04-01", "keyword": "HBM 공급 확대", "type": "bullish"},
            {"date": "2026-04-02", "keyword": "외국인 매수세", "type": "bullish"},
            {"date": "2026-04-03", "keyword": "경기 둔화 우려", "type": "bearish"},
            {"date": "2026-04-04", "keyword": "실적 기대감", "type": "bullish"},
            {"date": "2026-04-07", "keyword": "기관 차익실현", "type": "bearish"},
        ],
        "summary": "SK하이닉스는 HBM 독점 공급 지위와 어닝 서프라이즈 기대감으로 강세를 보이고 있으나, 글로벌 경기 둔화 우려가 상승 폭을 제한하고 있습니다.",
        "feedback": "HBM 시장 지배력이 견고하고 실적 모멘텀이 강한 만큼, 단기 조정 시 비중 확대를 고려할 수 있습니다. 다만 밸류에이션이 높아진 만큼 목표가 대비 현재가 위치를 확인하고 진입하는 것이 바람직합니다.",
    },
}

STATS = {
    "005930": {
        "market_cap": "426.7조",
        "per": 12.3,
        "pbr": 1.2,
        "dividend_yield": 2.1,
        "high_52w": 84000,
        "low_52w": 58200,
    },
    "000660": {
        "market_cap": "129.5조",
        "per": 8.7,
        "pbr": 1.8,
        "dividend_yield": 1.2,
        "high_52w": 235000,
        "low_52w": 120000,
    },
    "AAPL": {
        "market_cap": "$3.01T",
        "per": 28.5,
        "pbr": 45.2,
        "dividend_yield": 0.55,
        "high_52w": 210.50,
        "low_52w": 164.08,
    },
    "NVDA": {
        "market_cap": "$2.03T",
        "per": 65.3,
        "pbr": 38.7,
        "dividend_yield": 0.03,
        "high_52w": 950.00,
        "low_52w": 475.00,
    },
    "035720": {
        "market_cap": "18.7조",
        "per": 35.2,
        "pbr": 1.5,
        "dividend_yield": 0.3,
        "high_52w": 58000,
        "low_52w": 35000,
    },
}


def get_analysis(ticker: str) -> dict | None:
    return ANALYSES.get(ticker)


def get_stats(ticker: str) -> dict | None:
    return STATS.get(ticker)
```

- [ ] **Step 5: 즐겨찾기 목업 (인메모리)**

`backend/app/mocks/favorites.py`:

```python
_favorites: set[str] = {"005930", "NVDA"}


def get_favorites() -> list[str]:
    return list(_favorites)


def add_favorite(ticker: str) -> bool:
    _favorites.add(ticker)
    return True


def remove_favorite(ticker: str) -> bool:
    _favorites.discard(ticker)
    return True


def is_favorite(ticker: str) -> bool:
    return ticker in _favorites
```

- [ ] **Step 6: 종목 API 라우터**

`backend/app/api/stocks.py`:

```python
from fastapi import APIRouter, HTTPException

from app.mocks.stocks import search_stocks, get_stock
from app.mocks.prices import generate_prices
from app.mocks.analysis import get_stats
from app.mocks.favorites import is_favorite

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/search")
def search(q: str = ""):
    if not q:
        return []
    return search_stocks(q)


@router.get("/{ticker}")
def stock_detail(ticker: str):
    stock = get_stock(ticker)
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
    stats = get_stats(ticker)
    return {
        **stock,
        "is_favorite": is_favorite(ticker),
        "stats": stats,
    }


@router.get("/{ticker}/prices")
def stock_prices(ticker: str, days: int = 30):
    stock = get_stock(ticker)
    if not stock:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
    return generate_prices(ticker, days)
```

- [ ] **Step 7: 분석 API 라우터**

`backend/app/api/analysis.py`:

```python
from fastapi import APIRouter, HTTPException

from app.mocks.analysis import get_analysis

router = APIRouter(prefix="/api/stocks", tags=["analysis"])


@router.get("/{ticker}/analysis")
def stock_analysis(ticker: str, period: str = "weekly"):
    analysis = get_analysis(ticker)
    if not analysis:
        raise HTTPException(status_code=404, detail="분석 데이터가 없습니다")
    return analysis
```

- [ ] **Step 8: 즐겨찾기 API 라우터**

`backend/app/api/favorites.py`:

```python
from fastapi import APIRouter

from app.mocks.favorites import get_favorites, add_favorite, remove_favorite
from app.mocks.stocks import get_stock

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


@router.get("")
def list_favorites():
    tickers = get_favorites()
    stocks = []
    for ticker in tickers:
        stock = get_stock(ticker)
        if stock:
            stocks.append(stock)
    return stocks


@router.post("/{ticker}")
def add(ticker: str):
    add_favorite(ticker)
    return {"status": "added", "ticker": ticker}


@router.delete("/{ticker}")
def remove(ticker: str):
    remove_favorite(ticker)
    return {"status": "removed", "ticker": ticker}
```

- [ ] **Step 9: main.py에 라우터 등록**

`backend/app/main.py`를 수정:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.stocks import router as stocks_router
from app.api.analysis import router as analysis_router
from app.api.favorites import router as favorites_router

app = FastAPI(title="StockInsight API", version="0.1.0")

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
def health_check():
    return {"status": "ok"}
```

- [ ] **Step 10: API 동작 확인**

```bash
cd /Users/cwkim/Documents/workspace/cw-cy-stock/backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

확인:
- `http://localhost:8000/api/stocks/search?q=삼성` → 삼성전자 반환
- `http://localhost:8000/api/stocks/005930` → 삼성전자 상세
- `http://localhost:8000/api/stocks/005930/prices?days=10` → 주가 데이터
- `http://localhost:8000/api/stocks/005930/analysis` → 분석 결과
- `http://localhost:8000/api/favorites` → 즐겨찾기 목록
- `http://localhost:8000/docs` → Swagger UI 자동 생성 확인

- [ ] **Step 11: 커밋**

```bash
cd /Users/cwkim/Documents/workspace/cw-cy-stock
git add backend/
git commit -m "feat: add mock data and REST API endpoints (stocks, analysis, favorites)"
```

---

## Task 4: 프론트엔드 타입 정의 및 API 서비스

**Files:**
- Create: `frontend/src/types/stock.ts`
- Create: `frontend/src/services/api.ts`

- [ ] **Step 1: TypeScript 타입 정의**

`frontend/src/types/stock.ts`:

```typescript
export interface Stock {
  ticker: string;
  name: string;
  market: string;
  sector: string;
  current_price: number;
  change: number;
  change_percent: number;
  is_favorite?: boolean;
  stats?: StatsInfo;
}

export interface StatsInfo {
  market_cap: string;
  per: number;
  pbr: number;
  dividend_yield: number;
  high_52w: number;
  low_52w: number;
}

export interface PriceRecord {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface KeywordDetail {
  keyword: string;
  type: "bullish" | "bearish" | "neutral";
  detail: string;
  source: string;
  impact_level: "high" | "mid" | "low";
  duration: "short" | "mid" | "long";
}

export interface DailyKeyword {
  date: string;
  keyword: string;
  type: "bullish" | "bearish" | "neutral";
}

export interface Analysis {
  date: string;
  period_type: string;
  keywords: KeywordDetail[];
  daily_keywords: DailyKeyword[];
  summary: string;
  feedback: string;
}
```

- [ ] **Step 2: API 서비스 레이어**

`frontend/src/services/api.ts`:

```typescript
import type { Stock, PriceRecord, Analysis } from "@/types/stock";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}

export async function searchStocks(query: string): Promise<Stock[]> {
  return fetchJson(`/api/stocks/search?q=${encodeURIComponent(query)}`);
}

export async function getStock(ticker: string): Promise<Stock> {
  return fetchJson(`/api/stocks/${ticker}`);
}

export async function getStockPrices(
  ticker: string,
  days: number = 30
): Promise<PriceRecord[]> {
  return fetchJson(`/api/stocks/${ticker}/prices?days=${days}`);
}

export async function getAnalysis(
  ticker: string,
  period: string = "weekly"
): Promise<Analysis> {
  return fetchJson(`/api/stocks/${ticker}/analysis?period=${period}`);
}

export async function getFavorites(): Promise<Stock[]> {
  return fetchJson("/api/favorites");
}

export async function addFavorite(ticker: string): Promise<void> {
  await fetch(`${API_BASE}/api/favorites/${ticker}`, { method: "POST" });
}

export async function removeFavorite(ticker: string): Promise<void> {
  await fetch(`${API_BASE}/api/favorites/${ticker}`, { method: "DELETE" });
}
```

- [ ] **Step 3: 커밋**

```bash
cd /Users/cwkim/Documents/workspace/cw-cy-stock
git add frontend/src/types/ frontend/src/services/
git commit -m "feat: add TypeScript types and API service layer"
```

---

## Task 5: 공통 UI 컴포넌트 — 상단 네비게이션 + 종목 검색

**Files:**
- Create: `frontend/src/components/layout/top-nav.tsx`
- Create: `frontend/src/components/search/stock-search.tsx`

- [ ] **Step 1: 종목 검색 컴포넌트 (Command Palette 스타일)**

`frontend/src/components/search/stock-search.tsx`:

```tsx
"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "@/components/ui/command";
import { searchStocks } from "@/services/api";
import type { Stock } from "@/types/stock";

export function StockSearch() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Stock[]>([]);
  const router = useRouter();

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  useEffect(() => {
    if (query.length < 1) {
      setResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      const data = await searchStocks(query);
      setResults(data);
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  const handleSelect = (ticker: string) => {
    setOpen(false);
    setQuery("");
    router.push(`/stock/${ticker}`);
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-400 hover:border-slate-600 transition-colors"
      >
        <span>🔍</span>
        <span>종목 검색...</span>
        <kbd className="ml-2 rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-500">
          ⌘K
        </kbd>
      </button>
      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput
          placeholder="종목명 또는 티커를 입력하세요..."
          value={query}
          onValueChange={setQuery}
        />
        <CommandList>
          <CommandEmpty>검색 결과가 없습니다.</CommandEmpty>
          <CommandGroup heading="종목">
            {results.map((stock) => (
              <CommandItem
                key={stock.ticker}
                value={stock.ticker}
                onSelect={() => handleSelect(stock.ticker)}
              >
                <div className="flex items-center gap-3">
                  <span className="font-medium text-slate-50">
                    {stock.name}
                  </span>
                  <span className="text-sm text-slate-500">
                    {stock.ticker} · {stock.market}
                  </span>
                </div>
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </>
  );
}
```

- [ ] **Step 2: 상단 네비게이션**

`frontend/src/components/layout/top-nav.tsx`:

```tsx
import Link from "next/link";
import { StockSearch } from "@/components/search/stock-search";

export function TopNav() {
  return (
    <nav className="flex items-center justify-between border-b border-slate-800 bg-slate-950 px-6 py-3">
      <div className="flex items-center gap-4">
        <Link href="/" className="text-lg font-bold text-slate-50">
          📊 StockInsight
        </Link>
        <StockSearch />
      </div>
      <div className="flex items-center gap-4">
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

- [ ] **Step 3: 루트 레이아웃에 TopNav 추가**

`frontend/src/app/layout.tsx` 수정:

```tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { TopNav } from "@/components/layout/top-nav";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "StockInsight — 주식 분석 대시보드",
  description: "주식 종목의 상승/하락/보합 요인을 확인하고 AI 피드백을 받는 서비스",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" className="dark">
      <body className={`${inter.className} bg-slate-950 text-slate-50 min-h-screen`}>
        <TopNav />
        <main>{children}</main>
      </body>
    </html>
  );
}
```

- [ ] **Step 4: 확인 후 커밋**

```bash
cd frontend && npm run dev
```

브라우저에서 `http://localhost:3000` 확인:
- 상단 네비게이션에 "StockInsight" 로고, 검색 버튼, 즐겨찾기 링크 표시
- ⌘K로 검색 다이얼로그 열림 (백엔드 실행 중이어야 검색 동작)

```bash
cd /Users/cwkim/Documents/workspace/cw-cy-stock
git add frontend/src/components/ frontend/src/app/layout.tsx
git commit -m "feat: add top navigation and command palette stock search"
```

---

## Task 6: 메인 페이지 — 즐겨찾기 목록

**Files:**
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: 메인 페이지 구현**

`frontend/src/app/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getFavorites } from "@/services/api";
import type { Stock } from "@/types/stock";

export default function Home() {
  const [favorites, setFavorites] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getFavorites()
      .then(setFavorites)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="mb-2 text-2xl font-bold">⭐ 즐겨찾기 종목</h1>
      <p className="mb-8 text-sm text-slate-400">
        관심 종목을 선택하여 분석을 확인하세요. ⌘K로 종목을 검색할 수 있습니다.
      </p>

      {loading ? (
        <div className="text-slate-500">로딩 중...</div>
      ) : favorites.length === 0 ? (
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-8 text-center text-slate-400">
          즐겨찾기한 종목이 없습니다. 종목을 검색하여 추가해보세요.
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {favorites.map((stock) => (
            <Link
              key={stock.ticker}
              href={`/stock/${stock.ticker}`}
              className="group rounded-lg border border-slate-800 bg-slate-900 p-4 transition-colors hover:border-slate-600"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-semibold text-slate-50 group-hover:text-blue-400 transition-colors">
                    {stock.name}
                  </div>
                  <div className="text-sm text-slate-500">
                    {stock.ticker} · {stock.market}
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-semibold text-slate-50">
                    {stock.current_price.toLocaleString()}
                    {stock.market === "KRX" ? "원" : "$"}
                  </div>
                  <div
                    className={`text-sm ${
                      stock.change_percent >= 0
                        ? "text-green-400"
                        : "text-red-400"
                    }`}
                  >
                    {stock.change_percent >= 0 ? "▲" : "▼"}{" "}
                    {Math.abs(stock.change).toLocaleString()} (
                    {stock.change_percent >= 0 ? "+" : ""}
                    {stock.change_percent}%)
                  </div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 확인 후 커밋**

프론트+백엔드 모두 실행 상태에서 `http://localhost:3000` 확인:
- 삼성전자, NVIDIA 카드 표시 (기본 즐겨찾기)
- 카드 클릭 시 `/stock/{ticker}`로 이동

```bash
cd /Users/cwkim/Documents/workspace/cw-cy-stock
git add frontend/src/app/page.tsx
git commit -m "feat: add favorites list on main page"
```

---

## Task 7: 종목 대시보드 — 헤더 + 기간 탭

**Files:**
- Create: `frontend/src/components/stock/stock-header.tsx`
- Create: `frontend/src/components/stock/period-tabs.tsx`
- Create: `frontend/src/app/stock/[ticker]/page.tsx`

- [ ] **Step 1: 종목 헤더 컴포넌트**

`frontend/src/components/stock/stock-header.tsx`:

```tsx
"use client";

import type { Stock } from "@/types/stock";
import { addFavorite, removeFavorite } from "@/services/api";
import { useState } from "react";

interface Props {
  stock: Stock;
}

export function StockHeader({ stock }: Props) {
  const [isFav, setIsFav] = useState(stock.is_favorite ?? false);

  const toggleFavorite = async () => {
    if (isFav) {
      await removeFavorite(stock.ticker);
    } else {
      await addFavorite(stock.ticker);
    }
    setIsFav(!isFav);
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

- [ ] **Step 2: 기간 탭 컴포넌트**

`frontend/src/components/stock/period-tabs.tsx`:

```tsx
"use client";

const PERIODS = [
  { key: "daily", label: "일간" },
  { key: "weekly", label: "주간" },
  { key: "monthly", label: "월간" },
  { key: "quarterly", label: "분기" },
  { key: "semi_annual", label: "반기" },
  { key: "annual", label: "연간" },
];

interface Props {
  selected: string;
  onSelect: (period: string) => void;
}

export function PeriodTabs({ selected, onSelect }: Props) {
  return (
    <div className="flex gap-1 rounded-lg bg-slate-950 p-1">
      {PERIODS.map((p) => (
        <button
          key={p.key}
          onClick={() => onSelect(p.key)}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            selected === p.key
              ? "bg-slate-800 text-slate-50"
              : "text-slate-500 hover:text-slate-300"
          }`}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: 종목 대시보드 페이지 (뼈대)**

`frontend/src/app/stock/[ticker]/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getStock, getStockPrices, getAnalysis } from "@/services/api";
import type { Stock, PriceRecord, Analysis } from "@/types/stock";
import { StockHeader } from "@/components/stock/stock-header";
import { PeriodTabs } from "@/components/stock/period-tabs";

export default function StockDashboard() {
  const params = useParams();
  const ticker = params.ticker as string;

  const [stock, setStock] = useState<Stock | null>(null);
  const [prices, setPrices] = useState<PriceRecord[]>([]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [period, setPeriod] = useState("weekly");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([getStock(ticker), getStockPrices(ticker), getAnalysis(ticker, period)])
      .then(([s, p, a]) => {
        setStock(s);
        setPrices(p);
        setAnalysis(a);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [ticker, period]);

  if (loading || !stock) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-500">
        로딩 중...
      </div>
    );
  }

  return (
    <div>
      <StockHeader stock={stock} />
      <div className="px-6 py-3 border-b border-slate-800 bg-slate-900">
        <PeriodTabs selected={period} onSelect={setPeriod} />
      </div>
      <div className="flex">
        {/* Left: Chart + Keywords */}
        <div className="flex-[2] border-r border-slate-800 p-6">
          <div className="rounded-lg bg-slate-900 p-4 mb-4 h-[300px] flex items-center justify-center text-slate-500">
            차트 영역 (Task 8에서 구현)
          </div>
          <div className="text-slate-500 text-sm">
            키워드 영역 (Task 9에서 구현)
          </div>
        </div>
        {/* Right: Detail Panel */}
        <div className="flex-1 bg-slate-950 p-6">
          <div className="text-slate-500 text-sm">
            상세 패널 (Task 10에서 구현)
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 확인 후 커밋**

`http://localhost:3000/stock/005930` 접속:
- 종목 헤더 (삼성전자, 가격, 즐겨찾기 버튼) 표시
- 기간 탭 동작 확인
- placeholder 영역 표시

```bash
cd /Users/cwkim/Documents/workspace/cw-cy-stock
git add frontend/src/components/stock/ frontend/src/app/stock/
git commit -m "feat: add stock dashboard page with header and period tabs"
```

---

## Task 8: 캔들 + 라인 차트

**Files:**
- Create: `frontend/src/components/stock/price-chart.tsx`
- Create: `frontend/src/components/stock/chart-toggles.tsx`
- Modify: `frontend/src/app/stock/[ticker]/page.tsx`

- [ ] **Step 1: lightweight-charts 설치**

```bash
cd /Users/cwkim/Documents/workspace/cw-cy-stock/frontend
npm install lightweight-charts
```

- [ ] **Step 2: 차트 토글 컴포넌트**

`frontend/src/components/stock/chart-toggles.tsx`:

```tsx
"use client";

interface ToggleItem {
  key: string;
  label: string;
  color: string;
}

const TOGGLES: ToggleItem[] = [
  { key: "closeLine", label: "종가 라인", color: "#60a5fa" },
  { key: "ma5", label: "MA5", color: "#fbbf24" },
  { key: "ma20", label: "MA20", color: "#a78bfa" },
  { key: "ma60", label: "MA60", color: "#f472b6" },
];

interface Props {
  active: Record<string, boolean>;
  onToggle: (key: string) => void;
}

export function ChartToggles({ active, onToggle }: Props) {
  return (
    <div className="flex gap-3">
      {TOGGLES.map((t) => (
        <button
          key={t.key}
          onClick={() => onToggle(t.key)}
          className="flex items-center gap-1.5"
        >
          <div
            className={`h-4 w-8 rounded-full transition-colors ${
              active[t.key] ? "" : "bg-slate-700"
            }`}
            style={active[t.key] ? { backgroundColor: t.color } : {}}
          >
            <div
              className={`h-3.5 w-3.5 rounded-full bg-white transition-transform ${
                active[t.key] ? "translate-x-4" : "translate-x-0.5"
              }`}
              style={{ marginTop: "1px" }}
            />
          </div>
          <span
            className="text-xs"
            style={{ color: active[t.key] ? t.color : "#64748b" }}
          >
            {t.label}
          </span>
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: 캔들 + 라인 차트 컴포넌트**

`frontend/src/components/stock/price-chart.tsx`:

```tsx
"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type LineData,
  type Time,
  ColorType,
  CrosshairMode,
} from "lightweight-charts";
import type { PriceRecord } from "@/types/stock";

function calculateMA(data: PriceRecord[], period: number): LineData<Time>[] {
  const result: LineData<Time>[] = [];
  for (let i = period - 1; i < data.length; i++) {
    const slice = data.slice(i - period + 1, i + 1);
    const avg = slice.reduce((sum, d) => sum + d.close, 0) / period;
    result.push({ time: data[i].date as Time, value: Math.round(avg * 100) / 100 });
  }
  return result;
}

interface Props {
  prices: PriceRecord[];
  overlays: Record<string, boolean>;
  onCandleClick?: (date: string) => void;
}

export function PriceChart({ prices, overlays, onCandleClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || prices.length === 0) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0f172a" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "#1e293b" },
        horzLines: { color: "#1e293b" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      width: containerRef.current.clientWidth,
      height: 300,
    });
    chartRef.current = chart;

    // Candlestick
    const candleSeries = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderDownColor: "#ef4444",
      borderUpColor: "#22c55e",
      wickDownColor: "#ef4444",
      wickUpColor: "#22c55e",
    });
    const candleData: CandlestickData<Time>[] = prices.map((p) => ({
      time: p.date as Time,
      open: p.open,
      high: p.high,
      low: p.low,
      close: p.close,
    }));
    candleSeries.setData(candleData);

    // Close Line
    const seriesMap: Record<string, ISeriesApi<"Line">> = {};

    if (overlays.closeLine) {
      const lineSeries = chart.addLineSeries({
        color: "#60a5fa",
        lineWidth: 2,
        priceLineVisible: false,
      });
      const lineData: LineData<Time>[] = prices.map((p) => ({
        time: p.date as Time,
        value: p.close,
      }));
      lineSeries.setData(lineData);
      seriesMap.closeLine = lineSeries;
    }

    // MA lines
    const maConfig = [
      { key: "ma5", period: 5, color: "#fbbf24" },
      { key: "ma20", period: 20, color: "#a78bfa" },
      { key: "ma60", period: 60, color: "#f472b6" },
    ];
    for (const ma of maConfig) {
      if (overlays[ma.key] && prices.length >= ma.period) {
        const maSeries = chart.addLineSeries({
          color: ma.color,
          lineWidth: 1,
          priceLineVisible: false,
        });
        maSeries.setData(calculateMA(prices, ma.period));
        seriesMap[ma.key] = maSeries;
      }
    }

    // Click handler
    chart.subscribeClick((param) => {
      if (param.time && onCandleClick) {
        onCandleClick(param.time as string);
      }
    });

    // Resize
    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    chart.timeScale().fitContent();

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [prices, overlays, onCandleClick]);

  return <div ref={containerRef} className="rounded-lg overflow-hidden" />;
}
```

- [ ] **Step 4: 대시보드 페이지에 차트 연결**

`frontend/src/app/stock/[ticker]/page.tsx`의 차트 placeholder를 교체:

차트 영역 부분을 다음으로 교체:

```tsx
// 상단 import에 추가
import { PriceChart } from "@/components/stock/price-chart";
import { ChartToggles } from "@/components/stock/chart-toggles";

// 컴포넌트 내부에 state 추가
const [overlays, setOverlays] = useState<Record<string, boolean>>({
  closeLine: true,
  ma5: false,
  ma20: true,
  ma60: false,
});
const [selectedDate, setSelectedDate] = useState<string | null>(null);

const handleToggle = (key: string) => {
  setOverlays((prev) => ({ ...prev, [key]: !prev[key] }));
};

// JSX 차트 영역
<div className="mb-2">
  <ChartToggles active={overlays} onToggle={handleToggle} />
</div>
<PriceChart
  prices={prices}
  overlays={overlays}
  onCandleClick={setSelectedDate}
/>
```

- [ ] **Step 5: 확인 후 커밋**

`http://localhost:3000/stock/005930` 에서:
- 캔들스틱 차트 표시
- 종가 라인(파란색), MA20(보라색) 오버레이 표시
- 토글 ON/OFF 동작 확인
- 봉 클릭 시 날짜 선택 동작

```bash
cd /Users/cwkim/Documents/workspace/cw-cy-stock
git add frontend/
git commit -m "feat: add candlestick chart with line overlays and toggles"
```

---

## Task 9: 키워드 섹션 + 타임라인

**Files:**
- Create: `frontend/src/components/stock/keyword-tag.tsx`
- Create: `frontend/src/components/stock/keyword-section.tsx`
- Create: `frontend/src/components/stock/keyword-timeline.tsx`
- Create: `frontend/src/components/stock/ai-feedback.tsx`
- Modify: `frontend/src/app/stock/[ticker]/page.tsx`

- [ ] **Step 1: 키워드 태그 컴포넌트**

`frontend/src/components/stock/keyword-tag.tsx`:

```tsx
"use client";

import type { KeywordDetail } from "@/types/stock";

const TYPE_STYLES = {
  bullish: {
    bg: "bg-green-500/10",
    border: "border-green-500/30",
    text: "text-green-400",
  },
  bearish: {
    bg: "bg-red-500/10",
    border: "border-red-500/30",
    text: "text-red-400",
  },
  neutral: {
    bg: "bg-slate-500/10",
    border: "border-slate-500/30",
    text: "text-slate-400",
  },
};

interface Props {
  keyword: KeywordDetail;
  isSelected: boolean;
  onClick: () => void;
}

export function KeywordTag({ keyword, isSelected, onClick }: Props) {
  const style = TYPE_STYLES[keyword.type];
  return (
    <button
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs font-medium transition-all ${style.bg} ${style.border} ${style.text} ${
        isSelected ? "ring-2 ring-blue-500 ring-offset-1 ring-offset-slate-950" : "hover:brightness-125"
      }`}
    >
      {keyword.keyword}
    </button>
  );
}
```

- [ ] **Step 2: 키워드 섹션 (상승/하락/보합)**

`frontend/src/components/stock/keyword-section.tsx`:

```tsx
"use client";

import type { KeywordDetail } from "@/types/stock";
import { KeywordTag } from "./keyword-tag";

interface Props {
  keywords: KeywordDetail[];
  selectedKeyword: string | null;
  onSelect: (keyword: KeywordDetail) => void;
}

export function KeywordSection({ keywords, selectedKeyword, onSelect }: Props) {
  const bullish = keywords.filter((k) => k.type === "bullish");
  const bearish = keywords.filter((k) => k.type === "bearish");
  const neutral = keywords.filter((k) => k.type === "neutral");

  return (
    <div className="space-y-3">
      {bullish.length > 0 && (
        <div className="rounded-lg border border-green-500/30 bg-green-500/5 p-3">
          <div className="mb-2 text-sm font-semibold text-green-400">
            📈 상승 요인
          </div>
          <div className="flex flex-wrap gap-2">
            {bullish.map((k) => (
              <KeywordTag
                key={k.keyword}
                keyword={k}
                isSelected={selectedKeyword === k.keyword}
                onClick={() => onSelect(k)}
              />
            ))}
          </div>
        </div>
      )}
      {bearish.length > 0 && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3">
          <div className="mb-2 text-sm font-semibold text-red-400">
            📉 하락 요인
          </div>
          <div className="flex flex-wrap gap-2">
            {bearish.map((k) => (
              <KeywordTag
                key={k.keyword}
                keyword={k}
                isSelected={selectedKeyword === k.keyword}
                onClick={() => onSelect(k)}
              />
            ))}
          </div>
        </div>
      )}
      {neutral.length > 0 && (
        <div className="rounded-lg border border-slate-500/30 bg-slate-500/5 p-3">
          <div className="mb-2 text-sm font-semibold text-slate-400">
            ➡️ 보합 요인
          </div>
          <div className="flex flex-wrap gap-2">
            {neutral.map((k) => (
              <KeywordTag
                key={k.keyword}
                keyword={k}
                isSelected={selectedKeyword === k.keyword}
                onClick={() => onSelect(k)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: 키워드 타임라인 (차트 아래)**

`frontend/src/components/stock/keyword-timeline.tsx`:

```tsx
"use client";

import type { DailyKeyword } from "@/types/stock";

const TYPE_COLORS = {
  bullish: { bg: "bg-green-500/20", text: "text-green-400" },
  bearish: { bg: "bg-red-500/20", text: "text-red-400" },
  neutral: { bg: "bg-slate-500/20", text: "text-slate-400" },
};

interface Props {
  dailyKeywords: DailyKeyword[];
  selectedDate: string | null;
  onDateSelect: (date: string) => void;
}

export function KeywordTimeline({
  dailyKeywords,
  selectedDate,
  onDateSelect,
}: Props) {
  return (
    <div className="mt-2 border-t border-slate-800 pt-2">
      <div className="flex gap-1 overflow-x-auto">
        {dailyKeywords.map((dk) => {
          const colors = TYPE_COLORS[dk.type];
          const isSelected = selectedDate === dk.date;
          return (
            <button
              key={dk.date}
              onClick={() => onDateSelect(dk.date)}
              className={`flex flex-col items-center gap-1 rounded-md p-1.5 min-w-[80px] transition-colors ${
                isSelected ? "bg-slate-800" : "hover:bg-slate-900"
              }`}
            >
              <span className="text-[10px] text-slate-500">
                {dk.date.slice(5)}
              </span>
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] ${colors.bg} ${colors.text}`}
              >
                {dk.keyword}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: AI 피드백 컴포넌트**

`frontend/src/components/stock/ai-feedback.tsx`:

```tsx
interface Props {
  summary: string;
  feedback: string;
}

export function AiFeedback({ summary, feedback }: Props) {
  return (
    <div className="rounded-lg border border-purple-500/30 bg-purple-500/5 p-4">
      <div className="mb-2 text-sm font-semibold text-purple-400">
        🤖 AI 피드백 & 대책
      </div>
      <p className="mb-3 text-sm leading-relaxed text-slate-300">{summary}</p>
      <div className="rounded-md bg-slate-900/50 p-3">
        <div className="mb-1 text-xs font-medium text-purple-300">
          투자 전략 제안
        </div>
        <p className="text-sm leading-relaxed text-slate-300">{feedback}</p>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: 대시보드 페이지에 키워드 + AI 피드백 연결**

`frontend/src/app/stock/[ticker]/page.tsx` — 왼쪽 패널의 키워드/AI 영역 교체:

상단 import 추가:

```tsx
import { KeywordSection } from "@/components/stock/keyword-section";
import { KeywordTimeline } from "@/components/stock/keyword-timeline";
import { AiFeedback } from "@/components/stock/ai-feedback";
import type { KeywordDetail } from "@/types/stock";
```

state 추가:

```tsx
const [selectedKeyword, setSelectedKeyword] = useState<KeywordDetail | null>(null);
```

왼쪽 패널 JSX (차트 아래):

```tsx
{analysis && (
  <>
    <KeywordTimeline
      dailyKeywords={analysis.daily_keywords}
      selectedDate={selectedDate}
      onDateSelect={setSelectedDate}
    />
    <div className="mt-4">
      <KeywordSection
        keywords={analysis.keywords}
        selectedKeyword={selectedKeyword?.keyword ?? null}
        onSelect={setSelectedKeyword}
      />
    </div>
    <div className="mt-4">
      <AiFeedback summary={analysis.summary} feedback={analysis.feedback} />
    </div>
  </>
)}
```

- [ ] **Step 6: 확인 후 커밋**

`http://localhost:3000/stock/005930`:
- 차트 아래 날짜별 키워드 타임라인 표시
- 상승(초록)/하락(빨강)/보합(회색) 키워드 태그
- AI 피드백 카드
- 키워드 클릭 시 selected 상태

```bash
cd /Users/cwkim/Documents/workspace/cw-cy-stock
git add frontend/src/components/stock/ frontend/src/app/stock/
git commit -m "feat: add keyword sections, timeline, and AI feedback panel"
```

---

## Task 10: 상세 리포트 패널 + 주요 지표

**Files:**
- Create: `frontend/src/components/stock/detail-panel.tsx`
- Create: `frontend/src/components/stock/stats-card.tsx`
- Modify: `frontend/src/app/stock/[ticker]/page.tsx`

- [ ] **Step 1: 상세 리포트 패널**

`frontend/src/components/stock/detail-panel.tsx`:

```tsx
import type { KeywordDetail } from "@/types/stock";

const TYPE_LABELS = {
  bullish: { label: "상승 요인", color: "text-green-400" },
  bearish: { label: "하락 요인", color: "text-red-400" },
  neutral: { label: "보합 요인", color: "text-slate-400" },
};

const IMPACT_LABELS = { high: "높음", mid: "중간", low: "낮음" };
const DURATION_LABELS = { short: "단기", mid: "중기", long: "장기" };

interface Props {
  keyword: KeywordDetail | null;
}

export function DetailPanel({ keyword }: Props) {
  if (!keyword) {
    return (
      <div>
        <h2 className="mb-3 text-sm font-bold text-slate-50">📋 상세 리포트</h2>
        <p className="text-sm text-slate-600">
          ← 키워드를 클릭하면 여기에 상세 내용이 표시됩니다
        </p>
      </div>
    );
  }

  const typeInfo = TYPE_LABELS[keyword.type];

  return (
    <div>
      <h2 className="mb-3 text-sm font-bold text-slate-50">📋 상세 리포트</h2>
      <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
        <div className={`mb-1 text-xs font-medium ${typeInfo.color}`}>
          {typeInfo.label}
        </div>
        <h3 className="mb-3 text-base font-bold text-slate-50">
          {keyword.keyword}
        </h3>
        <p className="mb-4 text-sm leading-relaxed text-slate-300">
          {keyword.detail}
        </p>
        <div className="space-y-2 text-xs text-slate-500">
          <div>📰 출처: {keyword.source}</div>
          <div className="flex gap-4">
            <span>
              📊 영향도:{" "}
              <span className="text-slate-300">
                {IMPACT_LABELS[keyword.impact_level as keyof typeof IMPACT_LABELS]}
              </span>
            </span>
            <span>
              ⏱ 지속성:{" "}
              <span className="text-slate-300">
                {DURATION_LABELS[keyword.duration as keyof typeof DURATION_LABELS]}
              </span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 주요 지표 카드**

`frontend/src/components/stock/stats-card.tsx`:

```tsx
import type { StatsInfo } from "@/types/stock";

interface Props {
  stats: StatsInfo;
  market: string;
}

export function StatsCard({ stats, market }: Props) {
  const currency = market === "KRX" ? "원" : "$";
  const items = [
    { label: "시가총액", value: stats.market_cap },
    { label: "PER", value: `${stats.per}배` },
    { label: "PBR", value: `${stats.pbr}배` },
    { label: "배당수익률", value: `${stats.dividend_yield}%` },
    {
      label: "52주 최고",
      value: `${stats.high_52w.toLocaleString()}${currency}`,
      color: "text-green-400",
    },
    {
      label: "52주 최저",
      value: `${stats.low_52w.toLocaleString()}${currency}`,
      color: "text-red-400",
    },
  ];

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
      <h3 className="mb-3 text-sm font-bold text-slate-50">주요 지표</h3>
      <div className="grid grid-cols-2 gap-2 text-sm">
        {items.map((item) => (
          <div key={item.label} className="flex justify-between">
            <span className="text-slate-500">{item.label}</span>
            <span className={item.color ?? "text-slate-50"}>{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 대시보드 페이지에 연결**

`frontend/src/app/stock/[ticker]/page.tsx` — 오른쪽 패널 교체:

import 추가:

```tsx
import { DetailPanel } from "@/components/stock/detail-panel";
import { StatsCard } from "@/components/stock/stats-card";
```

오른쪽 패널 JSX:

```tsx
<div className="flex-1 bg-slate-950 p-6 space-y-4">
  <DetailPanel keyword={selectedKeyword} />
  {stock.stats && (
    <StatsCard stats={stock.stats} market={stock.market} />
  )}
</div>
```

- [ ] **Step 4: 확인 후 커밋**

`http://localhost:3000/stock/005930`:
- 키워드 클릭 → 오른쪽에 상세 리포트 (출처, 영향도, 지속성)
- 아래에 주요 지표 (시가총액, PER, PBR 등)

```bash
cd /Users/cwkim/Documents/workspace/cw-cy-stock
git add frontend/src/components/stock/ frontend/src/app/stock/
git commit -m "feat: add detail report panel and stats card"
```

---

## Task 11: 대시보드 페이지 최종 조립

**Files:**
- Modify: `frontend/src/app/stock/[ticker]/page.tsx`

- [ ] **Step 1: 전체 대시보드 페이지 완성본 작성**

`frontend/src/app/stock/[ticker]/page.tsx` 전체를 다음으로 교체:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getStock, getStockPrices, getAnalysis } from "@/services/api";
import type { Stock, PriceRecord, Analysis, KeywordDetail } from "@/types/stock";
import { StockHeader } from "@/components/stock/stock-header";
import { PeriodTabs } from "@/components/stock/period-tabs";
import { PriceChart } from "@/components/stock/price-chart";
import { ChartToggles } from "@/components/stock/chart-toggles";
import { KeywordTimeline } from "@/components/stock/keyword-timeline";
import { KeywordSection } from "@/components/stock/keyword-section";
import { AiFeedback } from "@/components/stock/ai-feedback";
import { DetailPanel } from "@/components/stock/detail-panel";
import { StatsCard } from "@/components/stock/stats-card";

export default function StockDashboard() {
  const params = useParams();
  const ticker = params.ticker as string;

  const [stock, setStock] = useState<Stock | null>(null);
  const [prices, setPrices] = useState<PriceRecord[]>([]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [period, setPeriod] = useState("weekly");
  const [loading, setLoading] = useState(true);

  const [overlays, setOverlays] = useState<Record<string, boolean>>({
    closeLine: true,
    ma5: false,
    ma20: true,
    ma60: false,
  });
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [selectedKeyword, setSelectedKeyword] = useState<KeywordDetail | null>(null);

  useEffect(() => {
    setLoading(true);
    setSelectedKeyword(null);
    setSelectedDate(null);
    Promise.all([
      getStock(ticker),
      getStockPrices(ticker),
      getAnalysis(ticker, period),
    ])
      .then(([s, p, a]) => {
        setStock(s);
        setPrices(p);
        setAnalysis(a);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [ticker, period]);

  const handleToggle = (key: string) => {
    setOverlays((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  if (loading || !stock) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-500">
        로딩 중...
      </div>
    );
  }

  return (
    <div>
      <StockHeader stock={stock} />
      <div className="border-b border-slate-800 bg-slate-900 px-6 py-3">
        <PeriodTabs selected={period} onSelect={setPeriod} />
      </div>

      <div className="flex min-h-[calc(100vh-180px)]">
        {/* Left Column */}
        <div className="flex-[2] border-r border-slate-800 p-6 space-y-4">
          <ChartToggles active={overlays} onToggle={handleToggle} />
          <PriceChart
            prices={prices}
            overlays={overlays}
            onCandleClick={setSelectedDate}
          />
          {analysis && (
            <>
              <KeywordTimeline
                dailyKeywords={analysis.daily_keywords}
                selectedDate={selectedDate}
                onDateSelect={setSelectedDate}
              />
              <KeywordSection
                keywords={analysis.keywords}
                selectedKeyword={selectedKeyword?.keyword ?? null}
                onSelect={setSelectedKeyword}
              />
              <AiFeedback
                summary={analysis.summary}
                feedback={analysis.feedback}
              />
            </>
          )}
        </div>

        {/* Right Column */}
        <div className="flex-1 bg-slate-950 p-6 space-y-4">
          <DetailPanel keyword={selectedKeyword} />
          {stock.stats && (
            <StatsCard stats={stock.stats} market={stock.market} />
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 전체 동작 확인**

백엔드 + 프론트엔드 모두 실행 상태에서:

1. `http://localhost:3000` — 즐겨찾기 목록 표시
2. ⌘K — 종목 검색 동작
3. 삼성전자 클릭 → 대시보드 이동
4. 캔들 차트 + 종가 라인 + MA20 표시
5. 차트 토글 ON/OFF 동작
6. 키워드 타임라인 날짜별 표시
7. 상승/하락/보합 키워드 태그 표시
8. 키워드 클릭 → 오른쪽 상세 리포트
9. AI 피드백 & 대책 표시
10. 주요 지표 카드 표시
11. ⭐ 즐겨찾기 토글 동작
12. 기간 탭 전환 동작

- [ ] **Step 3: 커밋**

```bash
cd /Users/cwkim/Documents/workspace/cw-cy-stock
git add frontend/src/app/stock/
git commit -m "feat: assemble complete stock dashboard with all components"
```

---

## Task 12: Docker 및 개발 환경 설정

**Files:**
- Create: `backend/Dockerfile`
- Create: `docker-compose.yml`
- Create: `frontend/.env.local`

- [ ] **Step 1: 백엔드 Dockerfile**

`backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: docker-compose.yml**

`docker-compose.yml`:

```yaml
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - PYTHONUNBUFFERED=1

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://backend:8000
    depends_on:
      - backend
```

- [ ] **Step 3: 프론트엔드 환경 변수**

`frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 4: .gitignore에 .env.local 추가 확인, 커밋**

`.gitignore`에 추가:

```
.env.local
node_modules/
.next/
```

```bash
cd /Users/cwkim/Documents/workspace/cw-cy-stock
git add backend/Dockerfile docker-compose.yml .gitignore
git commit -m "feat: add Docker setup and development environment config"
```

---

## 요약

| Task | 내용 | 예상 결과 |
|------|------|-----------|
| 1 | 프론트엔드 초기화 (Next.js + shadcn/ui + 다크 테마) | 빈 페이지 렌더링 |
| 2 | 백엔드 초기화 (FastAPI + health check) | /api/health 응답 |
| 3 | 백엔드 목업 데이터 + 전체 API | Swagger UI에서 모든 API 확인 |
| 4 | 프론트 타입 + API 서비스 | 타입 안전한 API 호출 레이어 |
| 5 | 상단 네비게이션 + ⌘K 종목 검색 | 검색 → 종목 선택 동작 |
| 6 | 메인 페이지 즐겨찾기 목록 | 카드 목록 → 클릭 이동 |
| 7 | 종목 대시보드 뼈대 (헤더 + 탭) | 종목 정보 + 기간 전환 |
| 8 | 캔들 + 라인 차트 | 차트 렌더링 + 토글 동작 |
| 9 | 키워드 섹션 + 타임라인 + AI 피드백 | 상승/하락 키워드 + 피드백 |
| 10 | 상세 리포트 패널 + 지표 | 키워드 클릭 → 상세 표시 |
| 11 | 대시보드 최종 조립 + 전체 테스트 | 풀 프로토타입 동작 |
| 12 | Docker + 환경 설정 | docker-compose 실행 가능 |
