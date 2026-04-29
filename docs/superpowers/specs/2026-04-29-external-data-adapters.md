# P1.5 — External Data Adapters (dartlab + SEC EDGAR)

작성일: 2026-04-29
브랜치: `feat/v2-external-data-adapters`
연관 문서:
- `docs/superpowers/specs/2026-04-28-ontology-aware-stock-card-design.md` (v2 메인 spec)
- `docs/superpowers/specs/2026-04-28-data-vs-analyst-split-refactor.md` (P1 refactor spec, 머지됨)
- `docs/research/2026-04-29-mcp-data-source-findings.md` (24 MCP 후보 비교)

---

## 1. Problem

P1 머지 후 카드는 **양쪽 시장 모두 작동**하지만 **데이터 깊이가 비대칭**이다. 2026-04-29 dartlab 0.9.26 직접 검증 결과:

| dartlab 결과 | KR (`005930`) | US (`TSLA`/`AAPL`) |
|---|---|---|
| `Company().rawFinance` | ✅ polars `(12722, 27)` 10년치 account-level | ❌ `AttributeError` |
| `Company().sector` | ✅ `SectorInfo(IT/반도체와반도체장비)` | ❌ `None` |
| `Company().fiscalYearEnd` | ✅ `'12-31'` | ❌ `None` (TSLA, AAPL 둘 다) |
| `Company().analysis(axis)` | ✅ 0.16s warm (시계열 dict 7-9 periods) | ✅ 2.2s cold / 0.7s warm |

원인은 dartlab의 EDGAR provider(`dartlab/providers/edgar/company.py`, 2615줄)가 DART provider(`dartlab/providers/dart/company.py`, 3651줄)보다 얇게 빌드된 것 + 0.9.26의 일부 추출 로직(예: `fiscalYearEnd` XBRL 태그) 버그. 0.9.X 패치 기다리는 것보다 우리가 SEC EDGAR API를 직접 호출하는 어댑터를 두는 게 견고하다.

또한 v2 카드의 데이터 fetch 경로가 현재 `services/analyst/data_layer.py` 안에서 DB 캐시 + Phase 1 collector(`yfinance`/`pykrx`/`naver`/외환 collector)에 직접 의존하고 있어, 외부 데이터 소스를 갈아끼우려면 분석 파이프라인 코드까지 만져야 한다. 추상화 레이어 부재.

추가로 dartlab의 MCP 도구 자체가 0.9.26에서 신뢰할 수 없다 — `companyFinancials`/`companyRatios`/`companyTopics`/`companyFilings`/`searchCompany` 도구가 dispatcher와 Company 클래스 비동기 또는 의존성 누락(`pyarrow`)으로 깨진 상태. **MCP 진입점은 우회**하고 dartlab Python 라이브러리 직접 의존이 필요하다.

## 2. Design Principles (locked)

이 10개는 spec 본문 작성 전에 사용자와 합의한 결정사항. 변경 시 spec 다시 본다.

1. **scope = dartlab 어댑터 + SEC EDGAR 어댑터 두 개 동시** (옵션 ②). KR/US 동등 데이터 표면 보장. KR-first → US-later 패턴 금지 (사용자 정정, 메모리 `feedback_kr_us_equal_priority.md`)
2. **dartlab 어댑터 진입점 = `Company().rawFinance` + `Company().analysis(axis)` 직접 호출**. MCP `_executeTool` 우회. 0.9.X 안정성 risk는 §13 escalation에 트래킹
3. **Per-ticker `Company` 인스턴스 LRU 캐시**: TTL 600s (dartlab 자체 default와 일치), max 5 인스턴스 (메모리 cap, 첫 로드 시 1.5GB 경고 관찰됨)
4. backend `pyproject.toml`에 `pyarrow` 의존성 추가
5. **Ticker normalization**: `.KS`/`.KQ`/`KRX:` 접미/접두 strip, KR 6자리 검증, US ticker uppercase, 형식 invalid 시 `ValueError` (silent fallback 없음)
6. **Cold-call prewarm**: favorites 종목을 시작 시 백그라운드 prefetch (US 첫 콜 ~21s 흡수)
7. **US 결손 보완은 SEC EDGAR 어댑터가 같은 마일스톤에서**: `rawFinance` (XBRL company facts) + `sector` (SIC + 정적 GICS 매핑) + `fiscalYearEnd` (XBRL `dei:CurrentFiscalYearEndDate`)
8. **KR/US 인터페이스는 비대칭 그대로 expose** (KR raw 더 풍부 / US는 SEC API 의존) + standard schema로 정규화. frontend는 양쪽 동일 schema만 보면 됨
9. **이름**: `app/services/external_data_adapters/` (NOT `external_mcps/`. dartlab은 라이브러리 호출이고 SEC EDGAR도 직접 SDK 호출 가능성 큼 — 둘 다 MCP 안 씀)
10. **Onto layer 자동 흐름**: 어댑터가 SectorInfo/industry raw를 표준 schema로 emit하면 `data_layer._fetch_relations_data`가 같은 sector 종목 peer 후보를 자동 등록. **본격 relation extraction pipeline은 P1.6** (별도 마일스톤)
11. **(eng-review) US 라우팅 = SEC EDGAR primary, dartlab fallback** — dartlab의 US `Company().fiscalYearEnd`/`sector`/`rawFinance`가 None/AttributeError이고 `companyAnalysis` cold 21s. SEC API는 무료/안정. dartlab은 `analysis(axis)` 결과만 보강 layer로 호출(있으면 사용)
12. **(eng-review) Cache cap=8, prewarm count=5** — prewarm이 cap을 모두 차지해 on-demand fetch가 prewarmed entry를 즉시 evict하는 충돌 방지. 차이 3 = 동시 분석 종목 buffer
13. **(eng-review) Cache 단위 = 데이터 결과(`FinancialSeries` 등) NOT `Company` 객체** — `Company` 인스턴스 1.5GB 관찰 × cap=5 = 7.5GB OOM 위험. 매 호출 새 `Company()` 생성(HF disk cache 후 0.45s) + 결과만 메모리 캐시. dartlab 자체 `_CACHE_TTL=600`도 별개 layer로 동작
14. **(eng-review) `InsiderActivity` schema/method는 P1.5 out of scope** — 카드 노출 X 상태로 schema/method만 작성하면 dead code. P1.6 spec 작성 시점에 데이터 표면 다시 보고 추가

## 3. Architecture

```
┌─ services/analyst/data_layer.py (P1, 그대로 유지) ─────────────────┐
│   assemble_data_layer(ticker)                                        │
│     - get_indicators(ticker)         ← Phase 1 collector            │
│     - get_macro_context()            ← Phase 1 collector            │
│     - _fetch_fundamentals(ticker)    ← DB                            │
│     - _fetch_recent_news(ticker)     ← DB                            │
│     - _fetch_relations_data(ticker)  ← DB                            │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ 새 의존성 (P1.5)
                           ▼
┌─ services/external_data_adapters/ (NEW) ────────────────────────────┐
│   __init__.py            — get_adapter_for(ticker) → router          │
│   base.py                — ExternalAdapter ABC + 표준 schema         │
│   ticker.py              — normalize_ticker + market 분기            │
│   dartlab_adapter.py     — KR DART (rawFinance + analysis + industry)│
│   sec_edgar_adapter.py   — US SEC (XBRL company facts + insider)    │
│   cache.py               — per-ticker LRU + TTL                      │
│   prewarm.py             — 시작 시 favorites 백그라운드 prefetch     │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌─ Standard schema (services/external_data_adapters/base.py) ─────────┐
│   FinancialSeries, SectorInfo, IdentityFacts, IndustryGraph,         │
│   FundamentalsSnapshot                                               │
└──────────────────────────────────────────────────────────────────────┘
```

기존 `data_layer`는 그대로 둠. P1.5는 새 어댑터 layer를 추가하고, **`data_layer`의 `_fetch_fundamentals` 만 어댑터 호출로 점진 전환** (§12 Migration).

ticker → 어댑터 라우팅 (§2 #11 결정):
- `^\d{6}$` (KR 6자리) → `DartlabAdapter` primary
- `^[A-Z]{1,5}$` (US 알파벳) → **`SecEdgarAdapter` primary**, `DartlabAdapter` boost layer (있으면 `analysis(axis)` 결과 merge, 실패 무시)
- 그 외 → `ValueError`

**US merge 정책**: SEC EDGAR이 항상 truth source (rawFinance/sector/fiscalYearEnd 책임). dartlab `analysis()`는 marginTrend/returnTrend 같은 가공 시계열만 enrichment로 추가. 두 어댑터 결과 충돌 시 SEC EDGAR 채택.

## 4. Standard Schema (Pydantic)

`services/external_data_adapters/base.py`에 정의. 모든 어댑터는 이 schema로만 emit. 어댑터 내부 구현(dartlab/SEC)은 외부에 노출 X.

```python
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

Market = Literal["KR", "US"]
PeriodType = Literal["annual", "quarterly", "ttm"]

class IdentityFacts(BaseModel):
    """종목 메타 — 카드 헤더에 박히는 정보."""
    ticker: str
    name: str
    market: Market
    currency: str            # "KRW" | "USD"
    fiscal_year_end: str | None  # "12-31" | "09-26" | None
    cik: str | None = None       # US만
    corp_code: str | None = None # KR만
    fetched_at: datetime
    source: str              # "dartlab" | "sec_edgar"

class SectorInfo(BaseModel):
    """sector 분류. dartlab SectorInfo / SEC SIC + GICS 매핑 통합 표면."""
    sector: str              # "IT" | "Financials" | ... (GICS top-level)
    industry_group: str | None
    confidence: float = Field(ge=0, le=1)
    source: Literal["dartlab", "sec_edgar_sic", "static_mapping"]

class FinancialSeries(BaseModel):
    """5y+ 재무 시계열. KR rawFinance / US XBRL company facts 정규화."""
    ticker: str
    period_type: PeriodType
    rows: list[dict]         # [{period: "2025", revenue: ..., op_income: ...}, ...]
    source: str
    fetched_at: datetime

class FundamentalsSnapshot(BaseModel):
    """단일 시점 재무 비율. data_layer._fetch_fundamentals 대체 후보."""
    per: float | None
    pbr: float | None
    market_cap: float | None
    dividend_yield: float | None
    per_5y_z: float | None
    period_label: str        # "2025Q3 분기" | "FY2024 annual"
    source: str

class IndustryGraph(BaseModel):
    """KR dartlab.industry() 산업지도 raw → onto 후보 source."""
    industry_id: str
    nodes: list[dict]        # [{stage: "design", name: "팹리스"}, ...]
    edges: list[dict]        # [{from: "design", to: "fab", relation: "supplies"}]
    source: Literal["dartlab"]
```

(§2 #14 결정: `InsiderActivity` schema는 P1.5 out of scope. P1.6 spec에서 추가.)

스키마는 v2 카드의 `Citation.source_type` 6종(`db|market_data|news|disclosure|web|curated_relation`)과 호환되어야 한다. 어댑터 출력은 모두 `disclosure`(공시 원천: DART/EDGAR) 또는 `market_data`(시세/재무 가공) source_type으로 매핑.

## 5. Adapter 1 — dartlab (KR primary + US boost layer)

진입점은 dartlab Python 라이브러리 직접 호출. **MCP `_executeTool` 우회.**

**캐시 단위 결정 (§2 #13)**: `Company` 객체를 캐시하지 **않음**. 객체 1.5GB × cap 5 = 7.5GB OOM 위험. 매 호출 새 `Company(ticker)` 생성 (dartlab의 HF disk cache 덕에 두 번째부터 0.45s) + 우리는 정규화된 결과(`IdentityFacts`/`FinancialSeries` 등)만 메모리 캐시 (§8.1). dartlab의 자체 `_CACHE_TTL=600` 객체 캐시는 별개 layer로 동작 — 영향 없음.

```python
# dartlab_adapter.py 핵심 함수
class DartlabAdapter(ExternalAdapter):
    async def fetch_identity(self, ticker: str) -> IdentityFacts:
        cached = self._cache.get((ticker, "identity"))
        if cached: return cached
        c = await asyncio.to_thread(_dartlab.Company, ticker)  # 0.45s warm
        result = IdentityFacts(
            ticker=c.stockCode, name=c.corpName,
            market=c.market,    # dartlab이 자동 KR/US 분기
            currency=c.currency,
            fiscal_year_end=getattr(c, "fiscalYearEnd", None),  # US는 None 가능 → SEC EDGAR가 채움
            corp_code=getattr(c, "corpCode", None) if c.market == "KR" else None,
            cik=getattr(c, "cik", None) if c.market == "US" else None,
            fetched_at=datetime.now(timezone.utc),
            source="dartlab",
        )
        self._cache.set((ticker, "identity"), result)
        return result

    async def fetch_financial_series(self, ticker: str) -> FinancialSeries:
        cached = self._cache.get((ticker, "financials"))
        if cached: return cached
        c = await asyncio.to_thread(_dartlab.Company, ticker)
        if c.market == "KR":
            df = c.rawFinance  # polars (12722, 27)
            rows = self._kr_rows_from_raw(df)  # bsns_year별 IS/BS/CF 통합
        else:
            # US는 c.rawFinance 없음 → c.analysis(axis)에서 history 추출 (boost only)
            margin = c.analysis("수익성")
            rows = self._us_rows_from_analysis(margin)
        result = FinancialSeries(...)
        self._cache.set((ticker, "financials"), result)
        return result

    async def fetch_sector(self, ticker: str) -> SectorInfo | None:
        # KR 한정 — US는 SEC EDGAR primary
        c = await asyncio.to_thread(_dartlab.Company, ticker)
        if c.market != "KR":
            return None
        si = c.sector  # SectorInfo(IT/반도체와반도체장비, conf=1.00)
        return SectorInfo(sector=si.sector, industry_group=si.industryGroup,
                          confidence=si.confidence, source="dartlab")

    async def fetch_industry_graph(self, industry_id: str) -> IndustryGraph:
        # KR 한정 — supply chain 관계 raw
        return IndustryGraph(...)
```

**MCP 도구 미사용 사유** (검증 결과):
- `companyFinancials` → `c.IS/BS/CF` AttributeError → "데이터 없음"
- `companyRatios` → `c.ratios` AttributeError
- `companyTopics` → DataFrame JSON serialize TypeError
- `companyFilings` → `topK` kwarg 미지원
- `searchCompany` → `pyarrow` 누락
- **작동 확인된 도구**: `companyProfile`, `companyAnalysis(axis)` — 단 우리는 Company 클래스 직접 더 자유롭게 접근

cold load latency: KR `005930` 첫 인스턴스 4.69s (HF 16.4MB 다운로드 포함), warm <10ms. US `TSLA` cold 0.55s (EDGAR 다운로드 포함), `AAPL` `companyAnalysis` cold 21.0s. **→ §8 prewarm 필수**.

## 6. Adapter 2 — SEC EDGAR (US 결손 보완)

dartlab의 US 결손 3개를 직접 채운다. SEC EDGAR public API는 무료 + API key 불필요(User-Agent 헤더만 필수).

```python
# sec_edgar_adapter.py 진입점
import os
from app.services.external_data_adapters.constants import (
    SIC_MAPPING_HIT_CONFIDENCE,    # 0.7 — SIC 코드는 거칠어서 보수적
    SIC_MAPPING_MISS_CONFIDENCE,   # 0.3 — 매핑 미스 시 명시적 저신뢰
    SEC_RATE_LIMIT_PER_SEC,        # 10
)

SEC_BASE = "https://data.sec.gov"

def _user_agent() -> str:
    """SEC 의무: 요청자 식별 가능한 User-Agent. env에서만 읽음."""
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        raise RuntimeError("SEC_USER_AGENT env 미설정 — .env.example 참조")
    return ua

class SecEdgarAdapter(ExternalAdapter):
    async def fetch_company_facts(self, cik: str) -> dict:
        # https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:0>10}.json
        # 단일 호출 → 5y+ XBRL company facts (Revenues, NetIncomeLoss, Assets, ...)

    async def fetch_financial_series(self, ticker: str) -> FinancialSeries:
        cik = await self._ticker_to_cik(ticker)  # 24h JSON cache
        facts = await self.fetch_company_facts(cik)
        rows = self._normalize_xbrl_to_rows(facts)  # us-gaap taxonomy 매핑
        if not rows:
            logger.warning("sec_edgar empty XBRL units for %s", ticker)  # silent fail 방지
        return FinancialSeries(rows=rows, source="sec_edgar", ...)

    async def fetch_sector(self, ticker: str) -> SectorInfo:
        # SEC submissions API의 sicCode → 정적 GICS 매핑
        sic = await self._fetch_sic(cik)
        gics = GICS_FROM_SIC.get(sic)
        if gics is None:
            return SectorInfo(sector="Unknown", industry_group=None,
                              confidence=SIC_MAPPING_MISS_CONFIDENCE,
                              source="sec_edgar_sic")  # silent fail X
        return SectorInfo(sector=gics, industry_group=None,
                          confidence=SIC_MAPPING_HIT_CONFIDENCE,
                          source="sec_edgar_sic")

    async def fetch_fiscal_year_end(self, ticker: str) -> str | None:
        # XBRL dei:CurrentFiscalYearEndDate
        ...
```

**Ticker → CIK 매핑 캐시**: SEC EDGAR `https://www.sec.gov/files/company_tickers.json` (전체 ticker→CIK 매핑) → 로컬 `app/data/sec_company_tickers.json`에 저장 + memory cache. **TTL 24h**, 백그라운드 refresh task로 갱신. 매핑 미스 시 `ValueError` (silent fallback X).

**라이브러리 결정**: SEC API는 매우 단순한 REST + JSON. 별도 SDK 없이 우리 `httpx` 클라이언트로 직접 호출. SEC EDGAR MCP server (조사 §6 Open Q #5의 AGPL 우려)도 우회. 자체 구현 ~200줄.

**SIC → GICS 매핑**: 정적 JSON 파일 `app/data/sic_to_gics.json`로 commit. 약 70개 매핑 row. 매핑 hit 시 `confidence=SIC_MAPPING_HIT_CONFIDENCE` (0.7), 미스 시 `SIC_MAPPING_MISS_CONFIDENCE` (0.3) + `sector="Unknown"` 반환 + log warning. 사유는 `constants.py` docstring에 명시.

**Rate limit**: SEC는 `SEC_RATE_LIMIT_PER_SEC` (10) req/sec 제한 — 우리 가족용 트래픽으론 영원히 안 걸림. 단 prewarm 시 burst 가능성 있어 `asyncio.Semaphore(8)` 가드.

(§2 #14: `fetch_insider_activity` method는 P1.5에서 제거. P1.6 spec에서 추가.)

## 7. Ticker normalization

`ticker.py`에 단일 함수.

```python
import re

KR_PATTERN = re.compile(r"^\d{6}$")
US_PATTERN = re.compile(r"^[A-Z]{1,5}$")
SUFFIX_RE = re.compile(r"\.(KS|KQ|KX)$|^KRX:", re.IGNORECASE)

def normalize_ticker(raw: str) -> tuple[str, Market]:
    """Yahoo/KRX 형식 변형을 정규화 + 시장 분기.

    Examples:
        '005930'        → ('005930', 'KR')
        '005930.KS'     → ('005930', 'KR')
        'KRX:005930'    → ('005930', 'KR')
        'TSLA'          → ('TSLA', 'US')
        'tsla'          → ('TSLA', 'US')
        '005930.US'     → ValueError
        '12345'         → ValueError (5자리)
    """
    s = SUFFIX_RE.sub("", raw.strip()).upper()
    if KR_PATTERN.match(s):
        return s, "KR"
    if US_PATTERN.match(s):
        return s, "US"
    raise ValueError(f"unknown ticker format: {raw!r}")
```

검증 결과 (이미 dartlab probe 4 시점):
- `'005930'` ✅, `'005930.KS'`/`'005930.KQ'` dartlab 거부 → strip 필요
- `'TSLA'`/`'AAPL'`/`'tsla'` 모두 자동 처리

frontend ticker 입력 / favorites / search는 모두 raw form 받고 우리가 normalize. seed.py도 normalize 통과 후 저장.

## 8. Cache & prewarm

### 8.1 Per-(ticker, method) 결과 LRU + per-key Lock

§2 #13 결정에 따라 **`Company` 객체 캐시 X, 정규화 결과만 캐시**. dartlab 자체 객체 캐시는 별개 layer.

`cache.py`:
```python
import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic

@dataclass
class _Entry:
    value: Any        # FinancialSeries / SectorInfo / IdentityFacts 등
    expires_at: float

class ResultCache:
    """Per-(ticker, method) 결과 LRU. asyncio.Lock per key로 동시 miss 방지."""

    def __init__(self, max_size: int = 8, ttl: int = 600) -> None:
        self._entries: OrderedDict[tuple, _Entry] = OrderedDict()
        self._locks: dict[tuple, asyncio.Lock] = {}
        self._max_size = max_size
        self._ttl = ttl

    async def get_or_fetch(self, key: tuple, fetcher: Callable[[], Awaitable]) -> Any:
        """동시 miss 시에도 fetcher는 1회만 실행."""
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            entry = self._entries.get(key)
            if entry and entry.expires_at > monotonic():
                self._entries.move_to_end(key)
                return entry.value
            value = await fetcher()
            self._entries[key] = _Entry(value, monotonic() + self._ttl)
            self._entries.move_to_end(key)
            self._evict_lru()
            return value

    def _evict_lru(self) -> None:
        while len(self._entries) > self._max_size:
            self._entries.popitem(last=False)
```

**파라미터 사유**:
- `max_size=8`: 동시 분석 5종목 + 1-2 prewarm 잔존 + 여유 1-2. §8.2 prewarm count(5)보다 크게 두어 **prewarm이 자기 자신을 evict하지 않게**.
- `ttl=600s`: dartlab 자체 default 일치. 시세 데이터 1분, 재무/sector/insider 더 길어도 OK이지만 단순화 위해 통일.

**메모리**: 결과 객체(`FinancialSeries` rows ~50KB, `SectorInfo` <1KB)만 보유 → 8 entries × 평균 50KB = 400KB 수준. dartlab `Company` 객체 1.5GB와 비교 불가능하게 안전.

### 8.2 Prewarm 백그라운드 작업

`prewarm.py`:
```python
PREWARM_LIMIT = 5  # cap=8과 의도적으로 차이 → on-demand fetch buffer 확보

async def prewarm_favorites(limit: int = PREWARM_LIMIT) -> dict[str, Any]:
    """애플리케이션 시작 시 favorites 상위 N개를 백그라운드 fetch.

    fastapi lifespan에서 호출. 실패는 무시 (나중에 on-demand fetch).
    """
    favs = await fetch_top_favorites(limit=limit)
    # SEC API rate limit 가드 (10 req/sec) — stagger
    sem = asyncio.Semaphore(8)

    async def _warm_one(ticker: str) -> None:
        async with sem:
            adapter = get_adapter_for(ticker)
            await adapter.fetch_identity(ticker)        # 가장 가벼운 호출
            await adapter.fetch_financial_series(ticker) # 실제 카드용 데이터

    results = await asyncio.gather(
        *(_warm_one(t) for t in favs), return_exceptions=True
    )
    return {"warmed": sum(1 for r in results if not isinstance(r, Exception))}
```

`app/main.py` lifespan에 `asyncio.create_task(prewarm_favorites())` 등록 (block X). favorites 테이블 활용 — 가족 사용자가 자주 보는 종목이 우선.

## 9. Onto layer 자동 흐름 (data → relations)

P1.5는 onto pipeline 직접 강화 X. 단 어댑터 산물이 자동으로 `stock_relations` / `macro_factors`에 흘러가는 **계약**을 명시.

### 자동 흐름 경로

새 종목 추가 시:
1. `Stock` row 저장 (frontend 또는 admin API)
2. **(NEW)** post-save hook이 어댑터 호출:
   - `adapter.fetch_identity(ticker)` → `Stock.sector`/`Stock.fiscal_year_end` 채움
   - `adapter.fetch_sector(ticker)` → `SectorInfo` confidence와 함께 저장
3. **(NEW)** 같은 sector 기존 종목 검색 → `peer` 후보 자동 등록 (`stock_relations`, `relation_type="peer"`, `strength=0.5`, `source="auto_sector_match"`)
4. KR이면 `adapter.fetch_industry_graph(industry_id)` → 산업지도 노드 매칭으로 `supply_upstream/downstream` 후보 추가
5. 기존 `llm_discover_relations`은 그대로 — web search 기반 보강 layer로 유지

### Confidence layering

같은 `(from, to)` 쌍의 다중 source는 `strength` 평균 + `source_count` 누적. 추후 P1.6 relation extraction pipeline이 이 confidence layering을 본격 사용.

### Concurrent writer 처리 (eng-review)

post-save hook (이번 spec)과 기존 `_bg_refresh_relations` (LLM web search 보강)이 같은 `stock_relations` 테이블에 동시 write 가능. duplicate row / race condition 방지:

- **DB constraint**: `stock_relations`에 `UNIQUE(from_stock_id, to_target, relation_type, source)` 추가 (alembic migration 신규)
- **Upsert**: 두 writer 모두 `on_conflict_do_update` 사용 — `(from, to, type, source)` 충돌 시 `strength` 평균 + `source_count` 증가 + `refreshed_at` 갱신
- **Source 분리**: post-save hook은 `source="auto_sector_match"` / `source="auto_industry_match"`, `_bg_refresh_relations`는 `source="llm_web_search"` — 별 row로 누적 (같은 (from, to) 다른 source는 conflict 아님)

### P1.5 acceptance for onto

- adapter 산물이 `stock_relations`에 row 추가하는 코드 경로 ✅
- 같은 sector peer 자동 등록이 `005930` + 새 KR 종목 1개 시나리오에서 동작 ✅
- US 신규 종목 추가 시 SEC EDGAR sector → 같은 sector peer 자동 등록 ✅
- 동시 writer 시 duplicate row 발생 안 함 ✅
- 본격 candidate vs verified 분리 / confidence scoring formula는 **P1.6 spec 별도** (out of scope)

## 10. File-by-file changes

### 신규 파일

```
backend/app/services/external_data_adapters/
├── __init__.py              # get_adapter_for(ticker) public API + ResultCache 싱글톤
├── base.py                  # ExternalAdapter ABC + standard schema (§4)
├── constants.py             # SIC_MAPPING_*_CONFIDENCE, SEC_RATE_LIMIT_PER_SEC 등 (§6)
├── ticker.py                # normalize_ticker + market 분기 (§7)
├── dartlab_adapter.py       # DartlabAdapter (§5)
├── sec_edgar_adapter.py     # SecEdgarAdapter (§6)
├── cache.py                 # ResultCache + asyncio.Lock per-key (§8.1)
└── prewarm.py               # prewarm_favorites (§8.2)

backend/app/data/
├── sic_to_gics.json         # SIC → GICS 정적 매핑 (§6, ~70 row)
└── sec_company_tickers.json # SEC EDGAR ticker→CIK cache (24h TTL, 백그라운드 갱신)

backend/alembic/versions/
└── XXXX_add_stock_relations_unique.py
                             # UNIQUE(from_stock_id, to_target, relation_type, source) 추가 (§9)

backend/tests/test_external_data_adapters/
├── test_ticker_normalize.py # §7 검증 — 8 케이스 unit
├── test_dartlab_adapter.py  # §5 — mock dartlab, 6 unit (KR/US identity, KR/US series, sector, AttributeError fallback)
├── test_sec_edgar_adapter.py # §6 — httpx mock, 7 unit (200/429/503/empty XBRL/ticker→CIK miss/SIC hit/SIC miss)
├── test_cache.py            # §8.1 — 5 unit (hit/miss/LRU/TTL/concurrent same-key Lock)
└── test_onto_flow.py        # §9 — 5 unit (KR auto peer / US auto peer / no peer / industry supply / concurrent writer)

backend/tests/integration/
└── test_smoke_us_apple.py   # AAPL real-API smoke (SEC EDGAR live), opt-in env=APPLE_SMOKE
```

### 수정 파일

```
backend/pyproject.toml
  + pyarrow                  # dartlab to_pandas 의존성
  + (이미 있음) httpx, pydantic

backend/app/services/analyst/data_layer.py
  ~ _fetch_fundamentals      # adapter 호출로 점진 전환 (§12)
  ~ _bg_refresh_relations    # source="llm_web_search" 명시 + on_conflict_do_update (§9)

backend/app/main.py
  + lifespan에 prewarm_favorites 백그라운드 task

backend/app/api/admin.py 또는 app/api/stocks.py
  + 신규 종목 추가 시 adapter post-save hook (§9)

backend/.env.example
  + SEC_USER_AGENT="StockInsight family-use <email>"  # SEC 의무

backend/app/models/relation.py
  + StockRelation에 source 컬럼 + UNIQUE(from_stock_id, to_target, relation_type, source) (§9)

.gitignore
  (이미 dartlab .mcp.json 처리됨)
```

총 신규 ~17 파일 (어댑터 8 + data 2 + alembic 1 + test 5 + smoke 1), 수정 6 파일.

## 11. Edge cases & invariants

| 케이스 | 처리 |
|---|---|
| `Company('005930.KS')` 거부 | `normalize_ticker`가 `.KS` strip 후 호출 (§7) |
| `Company().fiscalYearEnd` US `None` | US 라우팅이 SEC EDGAR primary (§3) — `fetch_fiscal_year_end` (XBRL `dei:CurrentFiscalYearEndDate`) |
| `Company().sector` US `None` | 동일 — SEC EDGAR `fetch_sector` (SIC + GICS 매핑) |
| `Company().rawFinance` US `AttributeError` | US primary는 SEC EDGAR `fetch_company_facts` → XBRL → rows. dartlab `analysis()`는 boost layer (있으면 merge, 없어도 OK) |
| dartlab 첫 호출 4.69s | KR 첫 종목은 cold. p95는 prewarm으로 흡수 (§8.2) |
| US AAPL `companyAnalysis` cold 21s | SEC EDGAR primary로 회피 (US는 dartlab `analysis()` boost 호출 실패해도 결과 영향 X) |
| dartlab 0.9.X 패치로 attribute 변경 | adapter 함수 안에 `getattr(c, "fiscalYearEnd", None)` 패턴 — 미래 호환. 깨지면 §14 escalation (오타 →) §13 |
| dartlab HF disk cache 깨짐 (parquet 손상) | `Company()` init 시 `RuntimeError` → adapter가 명시적 raise (silent fail X) + log error + alert hook |
| `Company` 인스턴스 메모리 1.5GB 경고 | §2 #13 결정에 따라 객체 캐시 X. 매 호출 새 인스턴스 후 GC. 결과(`FinancialSeries` 등)만 캐시 |
| 같은 ticker 동시 호출 (parallel `gather`) | `ResultCache`의 `asyncio.Lock` per-key가 중복 cold fetch 방지 (§8.1) |
| Cache cap vs prewarm 충돌 | `max_size=8, prewarm count=5` → 차이 3 buffer. prewarm이 자기 entry evict 불가 (§8.2) |
| SEC API 429 / 5xx | `httpx` 재시도 3회 + exponential backoff. 그래도 fail 시 cached stale 반환 + alert hook |
| SEC API 200 + empty XBRL units | rows=[] 반환 + log warning (silent quality 저하 방지) |
| ticker invalid | `normalize_ticker`에서 `ValueError` — silent fallback X |
| SIC 매핑 hit | `confidence=SIC_MAPPING_HIT_CONFIDENCE` (0.7, constants.py) |
| SIC 매핑 미스 | `confidence=SIC_MAPPING_MISS_CONFIDENCE` (0.3) + `sector="Unknown"` + log warning |
| Ticker → CIK lookup 실패 (US) | `app/data/sec_company_tickers.json` 24h cache 조회 후 미스 시 background refresh trigger + `ValueError` |
| `stock_relations` duplicate write (concurrent) | `UNIQUE(from, to, type, source)` + `on_conflict_do_update` (§9) |

## 12. Test plan

### Unit (31 cases)
- `test_ticker_normalize.py` — **8 케이스** (KR clean/KS strip/KQ strip/KRX prefix/US clean/US lowercase→upper/garbage→ValueError/empty→ValueError)
- `test_dartlab_adapter.py` — **6 케이스** (KR identity / KR series / US identity (fiscal_year_end=None graceful) / US series via analysis() boost / sector KR / dartlab `Company` AttributeError graceful)
- `test_sec_edgar_adapter.py` — **7 케이스** (XBRL 정상 200 / XBRL 200 + empty units → rows=[] + warning / 429 backoff / 503 retry exhaust → cached stale / ticker→CIK miss → ValueError / SIC hit confidence=0.7 / SIC miss confidence=0.3 + Unknown)
- `test_cache.py` — **5 케이스** (hit / miss → fetch / LRU evict (max=8 초과) / TTL evict (>600s) / **concurrent same-key 2 callers → fetcher 1회만 실행 (asyncio.Lock)**)
- `test_onto_flow.py` — **5 케이스** (KR new stock → SectorInfo → 같은 sector peer 자동 등록 / US new stock → SEC EDGAR sector → peer / 같은 sector 종목 0개 → peer 등록 X / KR industry node 매칭 → supply 후보 / **concurrent post-save hook + bg_refresh_relations → duplicate row 없음**)

### Adversarial (3 cases)
- dartlab 0.9.X에서 `Company().rawFinance` 사라진 시나리오 (mock AttributeError raises) → KR adapter 명시적 RuntimeError + alert hook
- SEC API 503 응답 → 재시도 3회 후 fail → cached stale 반환 + alert hook
- SIC 코드 mapping 미스 → confidence=0.3 + sector="Unknown" + log warning

### Property (2 cases)
- 같은 ticker 다양한 normalize 입력 (`'005930'`, `'005930.KS'`, `' 005930 '`)에 대해 같은 (ticker='005930', market='KR') 출력 (parametrize)
- 어댑터 출력은 `IdentityFacts`/`FinancialSeries` schema invariant 만족 (any attribute None가 아닌 required field 검증)

**Total: 31 + 3 + 2 = 36 cases.**

### Monitoring / alert hooks (P1.5에서 stub 정의, P1.6에서 본격 monitoring 통합)
adapter는 다음 critical fail 시 `alert_hook(event_type, ticker, detail)` 호출 (P1.5에서 stub은 log.error만):
- `dartlab_hf_cache_corrupt` — Company init RuntimeError
- `sec_api_exhausted` — 재시도 후도 실패
- `dartlab_attribute_missing` — 0.9.X 패치로 expected attribute 사라짐

### Integration smoke (real API, opt-in)
- `test_smoke_us_apple.py` — `pytest.mark.smoke + os.environ.get("APPLE_SMOKE")` 옵트인. AAPL을 SEC EDGAR API로 직접 조회 → `FinancialSeries` rows ≥ 5y, `fiscal_year_end="09-26"`, `sector="Information Technology"`. `SEC_USER_AGENT` env 필수.
- 기존 `test_smoke_005930.py` / `test_smoke_tsla.py` — adapter 도입 후에도 통과해야 (회귀 zero)

### 실행 명령
```bash
uv run pytest -m "not smoke" -q              # 모든 unit + adversarial + property
uv run pytest -m smoke -v                    # 005930 + TSLA + AAPL (real API)
```

## 13. Migration / rollout

### Phase A — adapter layer 도입만 (분석 파이프라인 unchanged)
1. `services/external_data_adapters/` 모듈 + 표준 schema + 두 어댑터 구현
2. unit + adversarial + property 테스트 그린
3. PR 1: "feat: external data adapter layer (no integration yet)"

### Phase B — `data_layer._fetch_fundamentals`만 어댑터 호출로 전환 (A/B)
1. 기존 collector 호출 + 새 어댑터 호출을 둘 다 실행, 결과 비교 로그
2. 1주일 운영 후 결과 일치도 확인
3. 어댑터 결과만 사용하도록 전환
4. PR 2: "feat: data_layer._fetch_fundamentals via external adapter"

### Phase C — 신규 종목 등록 시 sector/industry 자동 채움
1. `app/api/stocks.py` POST 종목 추가 endpoint에 post-save hook 추가
2. `stock_relations` 자동 peer 등록 (§9)
3. PR 3: "feat: auto-populate sector/onto on stock add"

### Phase D — prewarm
1. `app/main.py` lifespan에 prewarm task
2. PR 4: "feat: cold-call prewarm via favorites"

각 Phase는 별도 PR. 한 마일스톤 안에 4 PR. Phase A부터 main 머지 가능 (실제 분석 영향 X).

## 14. AGPL 검토

조사 §6 Open Q #5의 AGPL-3.0 우려는 **SEC EDGAR MCP server**(stefanoamorelli/sec-edgar-mcp) 채택 시. 우리는 §6 결정대로 **MCP server 미채택, SEC API 직접 httpx 호출**이라 AGPL 영향 없음.

dartlab은 Apache 2.0 — 자유 사용.

라이브러리 결정:
- dartlab Python package: Apache 2.0 ✅
- SEC EDGAR: 자체 httpx 구현 — 라이선스 N/A
- 정적 GICS 매핑 데이터: 우리 자체 작성 — 라이선스 N/A

**결론: AGPL 우려 클로즈. 별도 라이선스 검토 작업 없음.**

## 15. Acceptance criteria

이 spec의 P1.5 acceptance — Phase A 머지 시점에 이 16개 모두 ✅:

- [ ] `services/external_data_adapters/` 모듈 구조 §3 그대로 (8 신규 파일)
- [ ] `base.py`에 §4 standard schema 5개 (`IdentityFacts`/`SectorInfo`/`FinancialSeries`/`FundamentalsSnapshot`/`IndustryGraph`)
- [ ] `constants.py`에 `SIC_MAPPING_HIT_CONFIDENCE`(0.7) / `SIC_MAPPING_MISS_CONFIDENCE`(0.3) / `SEC_RATE_LIMIT_PER_SEC`(10) docstring 사유 명시
- [ ] `dartlab_adapter.py`: `fetch_identity` / `fetch_financial_series` / `fetch_sector` / `fetch_industry_graph` 4개 메서드 (객체 캐시 X, 결과 캐시만)
- [ ] `sec_edgar_adapter.py`: `fetch_company_facts` / `fetch_financial_series` / `fetch_sector` / `fetch_fiscal_year_end` 4개 메서드 (`USER_AGENT`는 env 기반)
- [ ] `ticker.py`: §7 8개 케이스 모두 통과
- [ ] `cache.py`: `ResultCache` `max_size=8` LRU + `ttl=600s` + per-key `asyncio.Lock` (concurrent fetch 1회 보장)
- [ ] `prewarm.py`: `PREWARM_LIMIT=5`, lifespan integration, 실패 무시 (나중에 on-demand fetch)
- [ ] `pyproject.toml` `pyarrow` 의존성 추가
- [ ] `.env.example`에 `SEC_USER_AGENT` 추가
- [ ] Alembic migration: `stock_relations`에 `source` 컬럼 + `UNIQUE(from_stock_id, to_target, relation_type, source)` (§9)
- [ ] Unit 31개 + Adversarial 3개 + Property 2개 = **36개** 모두 그린
- [ ] AAPL smoke 통과 (5y series + fiscal_year_end="09-26" + GICS sector "Information Technology")
- [ ] 기존 005930 + TSLA smoke도 회귀 zero
- [ ] dartlab MCP `_executeTool` import 절대 X (`grep -r "_executeTool" app/services/external_data_adapters/` 결과 비어있음)
- [ ] §9 onto 자동 흐름 시나리오 단위 테스트 5개 통과 (KR/US peer + concurrent writer 포함)

Phase B/C/D는 별도 acceptance (각 PR 안에서).

## 16. Out of scope

P1.5 안에서 **하지 않는 것** — P1.6+ 별도 마일스톤:

- 본격 relation extraction pipeline (candidate vs verified 분리, confidence scoring formula)
- pykrx-mcp 통합 (KR 투자자 수급 — 조사 §3.2 권고지만 후순위)
- FRED MCP 통합 (US macro — 조사 §3.5 권고지만 후순위)
- SEC Form 4 insider 카드 노출 (P1.5에서는 fetch만, 카드는 P1.6+)
- Yahoo Finance / Alpha Vantage / Finnhub 도입 (yfinance 비공식 위험 + 무료 quota)
- ETF holdings / fund flows (조사 §13)
- Korean news MCP (조사 §8 — 대체 어려움, 기존 `collectors/news.py` 유지)
- v2 frontend 카드 변경 (P2)
- Stock Universe 시각화 (P3)

---

## 다음 단계

1. ✅ plan-eng-review 2026-04-29 통과 (architecture/code/test/perf 4 review + 4 결정사항 본문 락인 §2 #11~14 + obvious fix 본문 적용)
2. Phase A 구현 — `services/external_data_adapters/` 모듈 + unit/adversarial/property **36 테스트**
3. Phase A PR → main 머지
4. Phase B/C/D 순차

작업량 추정: Phase A ~3-4일 (36 테스트 포함), B 1일+1주 운영, C 1일, D 0.5일. 합 ~1.5주 (smoke 안정화 포함).
