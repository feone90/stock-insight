# Findings

작성일: 2026-04-29  
대상: StockInsight 개인/가족용 주식 분석 카드의 데이터 소스 MCP 서버 후보 조사  
기준: 무료 또는 무료 티어 우선, KR/US 주식 지원 여부, 기존 FastAPI/PostgreSQL 백엔드에 부분 도입 가능한지 중심

## Executive Summary

이번 조사 결론은 단순함. MCP 서버가 이미 꽤 많지만, StockInsight의 핵심 백엔드를 통째로 대체할 정도로 안정적인 “무료, KR+US, 재무+뉴스+가격+관계” 통합 MCP는 아직 없음. 대신 특정 영역은 바로 도입 가치가 있음.

가장 현실적인 도입 순서는 다음과 같음.

1. **DartLab**: 이미 발견한 서버지만, KR DART와 US SEC 재무제표, 사업 설명, 리스크 팩터까지 묶어 제공하므로 `collectors/financials.py`의 얕은 재무 데이터 보강 1순위.
2. **pykrx-mcp**: KR 가격, OHLCV, PER/PBR/EPS/DIV/BPS/DPS, 투자자 수급을 무료로 가져올 수 있어 KR 가격/수급 레이어 보강에 적합.
3. **SEC EDGAR MCP**: US 10-K, 10-Q, 8-K, XBRL 재무제표, Form 3/4/5 내부자 거래까지 지원하므로 US 공시/재무/내부자 거래 보강에 적합.
4. **FRED MCP**: FRED 80만 개 이상 시계열을 MCP로 조회할 수 있어 `collectors/macro.py` 중 US10Y, CPI, Fed Funds, 경기 지표 쪽을 대체 또는 보강 가능.
5. **Yahoo Finance MCP 또는 Alpha Vantage MCP**: US 가격, OHLCV, 옵션, 뉴스, 회사 개요, 기술 지표 보강용. 다만 무료 API 제한과 yfinance 안정성 이슈 때문에 핵심 저장소의 단일 소스로 쓰기보다는 fallback/validation 용도가 적합.

반대로 당장 도입하지 않는 편이 나은 것도 있음. Unusual Whales, Polygon/Massive, Financial Modeling Prep, Financial Datasets는 기능은 강하지만 대부분 API key, 유료 플랜, 무료 티어 제한, 미국 중심 커버리지 문제가 있음. StockInsight가 “가족 3명용, 무과금 우선”이라는 조건이면 P1/P2에서는 과함.

---

## Section 1 — Survey

> 표 안의 maturity는 2026-04-29 기준으로 확인 가능한 GitHub/PyPI/README 신호만 적음. 일부 저장소는 GitHub UI가 동적으로 로딩되어 정확한 star/commit 수가 다르게 보일 수 있으므로, 채택 전 재확인이 필요함.

| # | MCP Server | Feature Fit | Data / Capabilities | License / Cost | Coverage | Maturity Signal | Install / MCP Entry Point | Limits / Notes |
|---|---|---|---|---|---|---|---|---|
| 0 | DartLab MCP<br>https://pypi.org/project/dartlab | 2, 4, 5 | KR DART, US SEC EDGAR, 재무제표, 비율, 공시, 사업 설명, 리스크, 거버넌스, macro/market scan 성격 도구 | Apache 2.0, 기본 무료. DART API fallback 시 DART quota 영향 | KR, US | PyPI 0.9.26, 2026-04-27 릴리스. MCP 25개 도구 제공 | `uv run dartlab mcp` 또는 remote SSE `https://eddmpython-dartlab.hf.space/mcp/sse` | 사용자가 이미 알고 있는 기준선. DART finance/docs 캐시 제공. 기존 `financials.py`를 가장 크게 대체할 후보 |
| 1 | pykrx-mcp<br>https://github.com/sharebook-kr/pykrx-mcp | 1, 2, 7, 9 | KOSPI/KOSDAQ/KONEX OHLCV, 시총, PER/PBR/EPS/DIV/BPS/DPS, 투자자별 거래대금, 공매도 | MIT, 무료. pykrx 기반 | KR | GitHub page 기준 소규모 저장소. commits 약 45, PyPI 0.1.3, 최근 commit 2026-02-01 확인 | `uvx pykrx-mcp` 또는 Claude config `command: uvx`, `args: ["pykrx-mcp"]` | pykrx 데이터 소스 변경/차단 리스크. KR 전용. 그래도 KR 투자자 수급은 매우 유용 |
| 2 | Korea Stock MCP Server<br>https://github.com/jjlabsio/korea-stock-mcp | 1, 2, 4, 7 | DART 공시 검색/원문 파싱, XBRL 재무 분석, KRX OHLCV/기본 종목 정보 | ISC. DART API key, KRX API key 필요 | KR | commits 100+ 수준. 한국 주식 특화 | `npx -y korea-stock-mcp@latest`, env `DART_API_KEY`, `KRX_API_KEY` | KRX API 승인 필요. 무료라도 키 발급/승인 절차 있음 |
| 3 | DART MCP Server<br>https://github.com/snaiws/DART-mcp-server | 2, 4 | DART 공시, 기업개황, 고유번호, 증자, 배당, 자기주식, 대주주, 임원 현황 | MIT. DART API key 필요 | KR | stars 약 9, tags/releases 14개, Docker 이미지 제공 | Smithery `npx -y @smithery/cli install snaiws/dart-mcp-server --client claude` 또는 Docker `snaiws/dart:latest` | DartLab보다 범위는 좁지만 DART 원천 API 직접 조회에 적합 |
| 4 | Korea Investment MCP<br>https://github.com/koreainvestment/koreainvestment-mcp | 1, 7, 10, 12, 13 | 한국투자증권 Open API 검색/설명용 MCP. 국내주식, 해외주식, 선물옵션, 채권, ETF/ETN API 카테고리 탐색 | 라이선스 확인 필요. 한국투자 API 계정 필요 가능성 높음 | KR, US, Asia | commits 약 6. 공식 조직 계정으로 보이나 기능은 “API search helper” 성격 | `uv sync`, `uv run server.py` | 실제 시장 데이터 fetcher라기보다 API 문서/엔드포인트 검색 도구에 가까움. 즉시 데이터 대체 후보는 아님 |
| 5 | SEC EDGAR MCP<br>https://github.com/stefanoamorelli/sec-edgar-mcp | 2, 4, 10 | SEC filings, company facts, 10-K/10-Q/8-K, XBRL BS/IS/CF, Form 3/4/5 insider trades, filing URLs | AGPL-3.0. SEC API 무료, User-Agent 필요 | US | PyPI/Conda 배포, v1.0.6. Docker 제공 | Docker env `SEC_EDGAR_USER_AGENT="Name email"` 또는 `python -m sec_edgar_mcp.server --transport streamable-http --port 9870` | AGPL 라이선스 주의. 내부 개인용이면 문제는 작지만 코드 결합 방식 확인 필요 |
| 6 | Alpha Vantage MCP<br>https://github.com/alphavantage/alpha_vantage_mcp | 1, 2, 5, 8, 12 | 주가, OHLCV, RSI 등 기술 지표, company overview, 일부 macro/FX/crypto | MIT. Alpha Vantage API key 필요. 무료 티어 제한 있음 | Global, US 중심 | Alpha Vantage 공식 저장소. 최근 업데이트 신호 있음 | Remote `https://mcp.alphavantage.co/mcp?apikey=KEY` 또는 local `uvx marketdata-mcp-server KEY` | 무료 호출량 제한 때문에 카드 생성마다 무제한 호출은 어려움 |
| 7 | Yahoo Finance MCP Server<br>https://github.com/laxmimerit/yahoo-finance-mcp-server | 1, 2, 3, 10, 12 | 실시간 주가, 재무제표, 뉴스, 옵션, holders, analyst recommendations, corporate actions | MIT, 무료. yfinance 비공식 소스 | Global, US 강함, 일부 KR ticker 가능성 | commits 약 7. PyPI/uvx 설치 지원 | `uvx yahoo-finance-mcp-server` 또는 `pip install yahoo-finance-mcp-server` | yfinance는 공식 API가 아니므로 rate limit/HTML 변경 리스크. 핵심 저장소 단일 소스는 비추천 |
| 8 | Yahoo Finance MCP by Alex2Yang97<br>https://github.com/Alex2Yang97/yahoo-finance-mcp | 1, 2, 3, 12 | historical OHLCV, stock info, news, actions | MIT, 무료. yfinance 기반 | Global, US 강함 | stars 270+ 수준, no releases 확인 | `uvx --from git+https://github.com/Alex2Yang97/yahoo-finance-mcp yahoo-finance-mcp` | 위와 동일하게 비공식 소스 리스크 |
| 9 | FRED MCP Server<br>https://github.com/stefanoamorelli/fred-mcp-server | 5 | FRED 800,000+ 경제 시계열 검색/조회 | AGPL-3.0. FRED API key 무료 | US macro 중심, 일부 global series | v1.0.2, Docker/Node 지원 | `node build/index.js` with `FRED_API_KEY`, Docker `stefanoamorelli/fred-mcp-server:latest` | US10Y, CPI, Fed Funds 등 macro 품질은 좋음. USD/KRW는 별도 확인 필요 |
| 10 | mcp-fred<br>https://github.com/cfdude/mcp-fred | 5 | FRED 전체 엔드포인트, 39 tools, project storage, async jobs, token safety | MIT. FRED API key 필요 | US macro 중심 | 0 star 수준의 신생 저장소. 기능 설명은 강함 | `pip install mcp-fred` 또는 `uv pip install mcp-fred` | 성숙도 낮음. 기능은 좋아 보이나 안정성 검증 필요 |
| 11 | Massive/Polygon MCP<br>https://github.com/massive-com/mcp_massive | 1, 5, 10, 12, 13 | stocks, options, futures, crypto, forex, economy, indices, composable query/search/call, technical functions | MIT. Massive/Polygon API key 필요. 대부분 유료성 | US/global market data | 공식 계열로 보이나 README에 experimental 표시 | `uv tool install "mcp_massive @ git+https://github.com/massive-com/mcp_massive@v0.9.1"`, `claude mcp add massive -e MASSIVE_API_KEY=... -- mcp_massive` | 기능은 강하지만 무료 제품 조건과 맞지 않음 |
| 12 | Financial Datasets MCP<br>https://github.com/financial-datasets/mcp-server | 1, 2, 3, 10 | stock prices, market news, income statement, balance sheet, cash flow, crypto | MIT. Financial Datasets API key 필요, pricing 확인 필요 | US 중심 | stars 약 2k, forks 300+로 maturity 우수 | Python 3.10+, `uv`, env `FINANCIAL_DATASETS_API_KEY`, `uv run server.py` | 무료/유료 경계 확인 필요. KR 커버리지 부족 가능성 |
| 13 | Financial Modeling Prep MCP<br>https://github.com/imbenrabi/Financial-Modeling-Prep-MCP-Server | 1, 2, 3, 5, 8, 10, 12, 13 | 250+ tools, 재무제표, ratios, quotes, technical indicators, SEC filings, insider/institutional, ETF/fund, analyst estimates, earnings, economic, social sentiment | Apache-2.0. FMP API key 필요. 무료 티어 제한/유료 가능성 높음 | US/global, KR 불확실 | stars 약 130, forks 40+. 도구 범위 매우 큼 | `npm install -g financial-modeling-prep-mcp-server`, env `FMP_ACCESS_TOKEN`, command `fmp-mcp` | 도구 수가 너무 많아 latency/token bloat 가능. P1에는 과함 |
| 14 | Finnhub MCP<br>https://github.com/cfdude/mcp-finnhub | 1, 2, 3, 6, 10, 11, 12 | quote, candles, fundamentals, estimates, ownership, ESG/social/supply chain, SEC filings, calendar, news sentiment | MIT. Finnhub API key, free tier 있음 | US/global, KR 제한 가능 | stars 약 6, no releases. 기능은 넓지만 신생 | source install `pip install -e .`, env `FINNHUB_API_KEY`, optional `FINNHUB_RATE_LIMIT_RPM` | Free RPM 낮음. supply chain/alternative data는 유료 플랜 가능성 확인 필요 |
| 15 | NewsAPI.ai MCP<br>https://github.com/eventregistry/newsapi-mcp | 3 | Search articles, track events, analyze news, real-time news intelligence | MIT. NewsAPI.ai key. free tier 2,000 tokens 수준 | Global news | npm 기반 공식성 있는 저장소 | `npx -y newsapi-mcp`, env `NEWSAPI_KEY` | 무료 토큰이 작아 운영용으로는 부족할 가능성 |
| 16 | News MCP Server<br>https://github.com/guangxiangdebizi/news-mcp | 3 | TheNewsAPI, NewsData.io, NewsAPI.org, GNews, Twingly 등을 smart failover로 조회 | Apache-2.0. 여러 뉴스 API key 필요 | Global, 다국어 | commits 약 3. 신생 | `npm install`, `npm run build`, MCP command `node build/index.js` | quota 자동 전환 아이디어는 좋지만 안정성 낮음. KR Naver 뉴스 대체는 어려움 |
| 17 | Brave Search MCP<br>https://github.com/brave/brave-search-mcp-server | 3, 8, Phase-A chat | web, local, image, video, news search, summarization, STDIO/HTTP | MIT. Brave API key 필요 | Global web/news | Brave 공식 MCP. Node 22+ | `npx -y @brave/brave-search-mcp-server --transport stdio`, env `BRAVE_API_KEY` | finance-specific 아님. Tavily 대체/보완 가능 |
| 18 | Tavily MCP<br>https://github.com/tavily-ai/tavily-mcp | 3, 8, Phase-A chat | search, extract, map, crawl. 웹 리서치용 | MIT. Tavily API key 필요 | Global web/news | commits 200+ 수준. official/prod-ready 표기 | Remote `https://mcp.tavily.com/mcp/?tavilyApiKey=KEY` 또는 `npx -y mcp-remote ...` | 이미 `tools.py::web_search`가 Tavily라면 MCP화는 코드 정리 효과만 큼 |
| 19 | Exa MCP<br>https://github.com/exa-labs/exa-mcp-server | 3, 6, 8, Phase-A chat | web search, company research, competitor research, code search, crawling | MIT. Exa API key 필요 | Global web/company | stars 4k+ 수준. hosted MCP 제공 | Hosted `https://mcp.exa.ai/mcp`, local `npx mcp-remote https://mcp.exa.ai/mcp?exaApiKey=KEY` | company research에는 좋지만 정량 데이터 소스는 아님 |
| 20 | Unusual Whales MCP<br>https://github.com/unusual-whales/unusual-whales-mcp | 10, 12, unknown unknowns | options flow, dark pool, congress trading, insider scanner, analyst tracker, earnings/economic calendar, volatility, sector flow | MIT. Unusual Whales API key. 유료 가능성 매우 높음 | US | v1.0.0 2026-03-02, stars 약 40+, official | Remote with `mcp-remote` and `Authorization: Bearer API_KEY` | 고가치지만 무료 제품 조건과 안 맞을 가능성이 큼 |
| 21 | StockScreen MCP<br>https://github.com/twolven/mcp-stockscreen | 8 | Yahoo Finance 기반 stock screener, technical/fundamental/options filters, watchlist 저장 | MIT. 무료, yfinance 기반 | US/global, KR 약함 | commits 약 12 | Python 3.12+, `pip install -r requirements.txt`, command `python stockscreen.py` | semantic screener의 초안에는 좋지만 KR/정확성 한계 |
| 22 | Reddit MCP Server<br>https://github.com/jordanburke/reddit-mcp-server | 11 | Reddit posts/comments/user info 조회, social sentiment 원천 수집 | MIT. Reddit API credentials 필요 | Global, US retail sentiment 강함 | npm 기반. social MCP 중 흔한 형태 | npm package 또는 local server 방식 | 감성 분석은 별도 구현 필요. Reddit ToS/API 정책 확인 필요 |
| 23 | Neo4j / Graphiti MCP 계열<br>https://github.com/neo4j-contrib/mcp-neo4j<br>https://github.com/getzep/graphiti | 6, unknown unknowns | 지식 그래프 조회, entity/relation memory, semantic/hybrid search | 오픈소스. Neo4j/Aura 또는 자체 DB 필요 | Data-agnostic | 공식/커뮤니티 성숙도는 비교적 높음 | 서버별 Python/uv 또는 Docker 방식 | “데이터 소스”가 아니라 relation storage/query layer. 직접 peer/supply chain 데이터를 만들어 넣어야 함 |

---

## Section 2 — By Feature

### 1. Single-stock card: current price, OHLCV, indicators
- KR: **pykrx-mcp**, **Korea Stock MCP**
- US/global: **Yahoo Finance MCP**, **Alpha Vantage MCP**, **Finnhub MCP**, **Financial Datasets MCP**, **FMP MCP**, **Polygon/Massive MCP**
- Recommendation: indicator 계산은 이미 `services/analyst/indicators.py`가 있으므로 MCP에서 RSI/ATR/MA를 받아오기보다 OHLCV만 가져오고 내부에서 deterministic하게 계산하는 편이 좋음.

### 2. Fundamentals: PER, PBR, market cap, dividend yield, ROE, 5y series
- KR: **DartLab**, **pykrx-mcp**, **Korea Stock MCP**, **DART MCP**
- US: **SEC EDGAR MCP**, **Yahoo Finance MCP**, **Alpha Vantage MCP**, **Financial Datasets MCP**, **FMP MCP**, **Finnhub MCP**
- Recommendation: `collectors/financials.py`는 가장 먼저 보강해야 하는 영역. 현재 PER/PBR/시총/배당 위주라면 DartLab/SEC EDGAR로 5y 재무제표 시계열을 추가하는 효과가 큼.

### 3. Recent news
- Global/US: **Brave Search MCP**, **Tavily MCP**, **Exa MCP**, **NewsAPI.ai MCP**, **News MCP**, **Yahoo Finance MCP**, **Finnhub MCP**, **FMP MCP**
- KR: 조사 범위 내에서 “Naver News 특화 MCP”는 뚜렷하게 확인되지 않음.
- Recommendation: KR 뉴스는 현재 `collectors/news.py` 유지. US 뉴스는 Tavily/Exa/Brave 중 하나를 MCP로 얇게 감싸면 Phase-A chat tool과도 공유 가능.

### 4. Recent disclosures
- KR: **DartLab**, **Korea Stock MCP**, **DART MCP**
- US: **SEC EDGAR MCP**, **DartLab**, **FMP MCP**, **Finnhub MCP**
- Recommendation: DART는 quota가 있고 공시 원문/첨부 파싱 latency가 길 수 있으므로, card 생성 시에는 “최근 공시 목록 + 요약 캐시” 방식이 적합.

### 5. Macro context
- **FRED MCP**, **mcp-fred**, **Alpha Vantage MCP**, **Finnhub MCP**, **FMP MCP**, **Polygon/Massive MCP**
- Recommendation: US10Y, CPI, Fed Funds, unemployment, recession indicators는 FRED가 가장 신뢰도 높음. VIX, USD/KRW, sector ETF는 기존 `collectors/macro.py`나 market data MCP 혼합이 필요.

### 6. Peer / supply-chain / theme / macro relations
- Direct relation source: **Finnhub MCP**의 supply chain/alternative data 가능성, **FMP MCP** 일부 company/industry 데이터
- Relation storage/query: **Neo4j MCP**, **Graphiti MCP**
- Web discovery: **Exa MCP**, **Tavily MCP**, **Brave Search MCP**
- Recommendation: 완전 대체는 어려움. `llm_discover_relations`를 바로 삭제하기보다, 관계 후보를 MCP/web에서 가져오고 LLM은 검증/설명만 하도록 역할을 줄이는 방향이 좋음.

### 7. Investor flow, KR-specific
- **pykrx-mcp**가 가장 직접적임.
- **Korea Stock MCP**는 KRX 기반이므로 확인 가치 있음.
- Recommendation: KR 투자자별 순매수는 pykrx-mcp를 우선 테스트.

### 8. Semantic screener
- **StockScreen MCP**, **FMP MCP**, **Finnhub MCP**, **Exa MCP**, **Tavily MCP**, **Financial Datasets MCP**
- Recommendation: P3/P4 이전에는 과투자하지 말 것. 먼저 PostgreSQL에 card snapshot을 쌓고 내부 SQL/vector 검색으로 만드는 편이 안정적임.

### 9. Sector-relative metrics
- **pykrx-mcp**: KR fundamentals
- **Yahoo Finance MCP**, **Alpha Vantage MCP**, **Financial Datasets MCP**, **FMP MCP**, **Finnhub MCP**: US/company metrics
- Recommendation: sector classification과 peer universe는 별도 테이블이 필요. MCP는 raw metric 공급원일 뿐 Good/Bad label은 내부 rule layer로 남겨야 함.

### 10. Insider trades, institutional holdings, analyst estimates / price targets
- **SEC EDGAR MCP**: US insider Form 3/4/5
- **Yahoo Finance MCP**: holders, analyst recommendations
- **Finnhub MCP**, **FMP MCP**, **Unusual Whales MCP**: estimates, ownership, analyst, insider
- Recommendation: US 고급 데이터는 무료 제한이 많음. SEC EDGAR Form 4부터 무료로 시작.

### 11. Social sentiment
- **Reddit MCP**, **Finnhub MCP**, **FMP MCP**, **Unusual Whales MCP**
- Recommendation: social sentiment는 noise가 커서 P1/P2 범위 밖. 추가하더라도 “참고 신호”로만.

### 12. Earnings calendar with consensus estimates
- **Finnhub MCP**, **FMP MCP**, **Unusual Whales MCP**, **Yahoo Finance MCP**, **Alpha Vantage MCP**
- Recommendation: 무료 티어 확인 후 US만 제한적으로 도입. KR 실적 캘린더는 별도 수집 필요 가능성 큼.

### 13. ETF holdings, fund flows
- **FMP MCP**, **Polygon/Massive MCP**, **Unusual Whales MCP**, **Financial Datasets MCP**
- Recommendation: P5 이후. 무과금 기준에서는 도입 우선순위 낮음.

---

## Section 3 — Replace-or-Augment Analysis

### 3.1 `collectors/financials.py`

현재 상태가 PER/PBR/시총/배당 정도라면, 가장 먼저 손볼 파일임.

**Adopt DartLab**
- 삭제/축소 가능:
  - 단일 시점 PER/PBR/배당만 반환하는 얕은 financial collector 로직
  - DART/SEC 원문을 따로 web search로 찾는 임시 로직
- 새로 남겨야 하는 것:
  - StockInsight 내부 표준 스키마로 mapping하는 adapter
  - 5y series, latest quarter, TTM, z-score 계산
  - KR/US ticker to corp/cik 매핑 캐시
- Trade-off:
  - 재무 데이터 깊이는 크게 좋아짐.
  - 하지만 MCP 호출 latency와 DART quota, cache freshness는 직접 관리 필요.

**Adopt SEC EDGAR MCP for US**
- 삭제/축소 가능:
  - US SEC filings를 Tavily/web search로 찾는 로직
  - 내부자 거래를 아직 수집하지 않는 공백
- 새로 추가:
  - Form 10-K/10-Q company facts normalization
  - Form 4 insider trade summary
- Trade-off:
  - AGPL 라이선스 확인 필요.
  - SEC User-Agent 설정 필수.

### 3.2 `collectors/stocks.py`

**Adopt pykrx-mcp for KR**
- 삭제/축소 가능:
  - pykrx-like 직접 호출 코드 중 OHLCV, market cap, investor flow 조회 부분
- 유지 권장:
  - ticker normalization
  - DB cache
  - retry/fallback
  - indicator 계산
- Trade-off:
  - MCP가 pykrx wrapper라면 직접 pykrx를 쓰는 것과 본질은 비슷함.
  - 이미 pykrx 코드를 잘 통제하고 있다면 “대체”보다 “external adapter로 병행 테스트”가 맞음.

**Adopt Yahoo/Alpha/Finnhub for US**
- 삭제/축소 가능:
  - yfinance-like 직접 호출 중 일부
- 유지 권장:
  - indicator 계산
  - quote snapshot 저장
  - fallback chain
- Trade-off:
  - yfinance wrapper는 깨질 수 있음.
  - Alpha/Finnhub는 API key와 quota가 있음.

### 3.3 `collectors/news.py`, `collectors/us_news.py`

**Adopt Tavily MCP / Exa MCP / Brave Search MCP**
- 삭제/축소 가능:
  - `tools.py::web_search`의 vendor-specific wrapper 일부
  - US news custom collector의 단순 웹 검색 부분
- 유지 권장:
  - Naver News KR collector
  - topic/sentiment/impact classifier
  - deduplication, URL canonicalization
- Trade-off:
  - MCP search는 “뉴스 API”라기보다 “웹 리서치 도구”임.
  - card의 deterministic news section에는 source/date/URL이 명확한 현재 collector가 더 안정적일 수 있음.

### 3.4 `collectors/disclosures.py`

**Adopt DartLab / DART MCP / Korea Stock MCP**
- 삭제/축소 가능:
  - DART 공시 목록 조회와 원문 fetch 중복 구현
- 유지 권장:
  - DART_API_KEY 관리
  - 최근 30일 공시 필터
  - 공시 중요도 분류
  - DB cache
- Trade-off:
  - DART MCP는 한국 공시에 특화되어 좋지만, DartLab이 더 넓은 재무/문서 요약 기능을 제공함.
  - 둘 다 DART API quota/latency 이슈에서 자유롭지는 않음.

### 3.5 `collectors/macro.py`, `collectors/exchange_rates.py`

**Adopt FRED MCP**
- 삭제/축소 가능:
  - US10Y, CPI, Fed Funds, unemployment 등 FRED에서 안정적으로 가져올 수 있는 macro series fetcher
- 유지 권장:
  - VIX, USD/KRW, sector ETF 가격 fetcher
  - 카드용 요약 indicator
  - local fallback cache
- Trade-off:
  - FRED는 macro 신뢰도가 좋지만 KR FX/ETF/시장 데이터 전체를 커버하지 않음.

### 3.6 `services/analyst/tools.py::llm_discover_relations`

**Adopt Finnhub / Exa / Graphiti or Neo4j**
- 삭제/축소 가능:
  - LLM이 아무 근거 없이 peer/theme/supply-chain 관계를 생성하는 부분
- 유지 권장:
  - 내부 relation table
  - relation confidence scoring
  - “verified by source” flag
  - LLM narrative generation
- Trade-off:
  - 무료로 좋은 relation graph를 주는 MCP는 아직 거의 없음.
  - 가장 현실적인 구조는 `candidate_relations = MCP/web + curated table`, `LLM = explanation only`.

---

## Section 4 — Unknown Unknowns

조사하면서 기존 section 2에 없지만 analyst card에 넣으면 차별화될 수 있는 범주가 보였음.

### 4.1 Options flow, dark pool, volatility surface
- 대표 MCP: **Unusual Whales MCP**, **Polygon/Massive MCP**
- 가치:
  - 단기 수급, 기관성 옵션 거래, unusual volume 탐지
  - earnings 전후 expected move 해석
- 주의:
  - 거의 US 중심이고 유료 가능성이 높음.
  - Buffett-style 장기 분석과는 결이 다르므로 “단기 이벤트 risk” 탭에만 제한하는 편이 좋음.

### 4.2 Congressional trading, government trading
- 대표 MCP: **Unusual Whales MCP**, **FMP MCP**
- 가치:
  - 미국 정치인 매매, 정부 계약, 규제 민감 산업의 이벤트 신호
- 주의:
  - 과대해석 위험이 큼.
  - 개인용 카드에서는 “참고 이벤트” 수준이 적절.

### 4.3 Insider Form 4 summary
- 대표 MCP: **SEC EDGAR MCP**
- 가치:
  - 무료로 접근 가능한 고신뢰 US insider signal
  - analyst estimates보다 비용 부담 낮음
- 권장:
  - US 카드의 “Recent corporate actions / insider activity” 섹션으로 추가 가치 높음.

### 4.4 Knowledge graph memory layer
- 대표 MCP: **Neo4j MCP**, **Graphiti MCP**
- 가치:
  - peer, supplier, customer, theme, macro sensitivity 관계를 누적 저장
  - card follow-up chat에서 “왜 이 종목이 연결돼?”를 설명 가능
- 주의:
  - 원천 데이터를 자동으로 만들어주지는 않음.
  - relation extraction pipeline을 별도로 설계해야 함.

### 4.5 Central bank / macro speech retrieval
- 대표 MCP:
  - 직접 특화 MCP는 뚜렷하지 않았으나 **FRED MCP + Exa/Tavily/Brave Search MCP** 조합 가능
- 가치:
  - FOMC, Fed speeches, BoK 관련 발언을 macro narrative에 반영
- 주의:
  - 실시간 뉴스/문서 검색 기반이므로 citation과 date filter가 매우 중요.

### 4.6 ETF holdings and factor exposure
- 대표 MCP: **FMP MCP**, **Financial Datasets MCP**, **Polygon/Massive MCP**
- 가치:
  - “이 종목이 어떤 ETF에서 얼마나 큰 비중인가”
  - theme exposure card에 좋음
- 주의:
  - 무료 티어에서 ETF holdings가 열려 있는지 확인 필요.

---

## Section 5 — Top Recommendations

### 1. DartLab MCP

가장 먼저 테스트할 가치가 있음. 이미 사용자가 발견한 서버이지만, 이번 조사 기준으로도 StockInsight의 `collectors/financials.py`를 가장 크게 단순화할 수 있는 후보임. 현재 financial collector가 PER/PBR/시총/배당 정도라면, DartLab은 KR DART와 US SEC 기반 재무제표, business description, risk factors까지 제공하므로 “정량 재무 + 공시 근거 + LLM 해석” 구조에 잘 맞음. 특히 5y series, z-score, contradiction detection의 입력 품질을 올리는 데 효과가 큼. 단, 바로 삭제하지 말고 `services/external_mcps/dartlab_adapter.py`를 만들어 기존 schema와 나란히 비교하는 A/B 방식이 좋음.

### 2. pykrx-mcp

KR 주식 카드의 가격, OHLCV, market cap, fundamentals, 투자자별 순매수에 바로 붙일 수 있는 무료 후보임. 특히 StockInsight section 2의 item 7, 즉 외국인/기관 수급은 US MCP들이 대부분 못 채우는 한국 특화 영역임. 다만 pykrx 자체가 비공식/스크래핑 성격이 있어 장애나 구조 변경에 취약할 수 있음. 그래서 기존 `collectors/stocks.py`를 전면 교체하기보다, pykrx-mcp 결과와 현재 collector 결과를 비교하고 투자자 수급만 먼저 채택하는 방식이 적합함.

### 3. SEC EDGAR MCP

US 종목의 공시, XBRL 재무제표, Form 3/4/5 insider trades를 무료 공식 원천 기반으로 확장할 수 있음. 특히 현재 item 10이 out of scope였던 insider trades를 큰 비용 없이 카드에 추가할 수 있다는 점이 좋음. 기존 US financial/news collector와 겹치는 부분은 있지만, SEC filing URL과 XBRL company facts는 analyst card의 cited evidence 품질을 높여줌. 다만 AGPL 라이선스라서 서버를 직접 수정/배포하거나 코드 결합할 때 주의가 필요함. 개인용 로컬 사용이면 리스크는 낮지만 확인은 필요함.

### 4. FRED MCP

`collectors/macro.py`의 US macro data를 안정적으로 보강할 수 있음. VIX, sector ETF, USD/KRW까지 모두 해결되지는 않지만, US10Y, Fed Funds, CPI, unemployment, recession indicators 같은 macro context는 FRED가 신뢰도와 커버리지 면에서 좋음. StockInsight의 “macro context”가 단순 가격 지표를 넘어 “왜 지금 valuation multiple이 눌리는지”를 설명하려면 FRED series가 유용함. 카드 latency를 줄이기 위해 매 요청마다 조회하지 말고 일 단위 cache를 두는 것을 권장함.

### 5. Tavily MCP or Exa MCP

이미 Tavily를 `services/analyst/tools.py::web_search`로 쓰고 있다면 Tavily MCP는 기능 확장보다는 구조 정리 효과가 큼. 반면 Exa는 company research와 competitor discovery에 강점이 있어 relation discovery를 보강할 수 있음. 둘 중 하나를 “Phase-A chat tools”용 MCP로 통일하면, card 생성 이후 follow-up chat에서 같은 검색 도구를 재사용하기 좋음. 단, deterministic card data에는 바로 쓰지 말고 “증거 보강, relation 후보 탐색, 뉴스 원문 확인” 레이어로 제한하는 편이 좋음.

---

## Section 6 — Anti-recommendations

### 1. Unusual Whales MCP: 기능은 강하지만 지금은 과함

options flow, dark pool, congress trading, analyst tracker, earnings calendar까지 있어 매력적임. 하지만 US 중심이고 API key/유료 가능성이 높아 “가족 3명용, 무과금 우선” 조건과 맞지 않을 수 있음. 장기적으로는 unknown unknowns 탭에 가치가 있지만, P1/P2에서는 도입하지 않는 편이 좋음.

### 2. Polygon/Massive MCP: professional data stack에 가깝지만 무료 제품에는 부담

시장 데이터 커버리지는 강하지만 API key와 유료 플랜 의존도가 높음. stocks/options/crypto/forex/economy까지 제공하는 만큼 도구 수와 schema도 크고, 처음부터 붙이면 latency와 복잡도가 올라갈 가능성이 큼. 무료 티어로는 필요한 호출량을 감당하기 어려울 수 있음.

### 3. Financial Modeling Prep MCP: broad하지만 tool bloat 위험

250개 이상의 tools와 24개 카테고리는 매력적이지만, 실제 카드 생성에는 필요한 도구가 10개 미만일 가능성이 높음. 너무 많은 MCP tools를 LLM에 노출하면 tool selection 비용, latency, hallucinated tool call 가능성이 올라감. 쓰더라도 직접 LLM에 전부 노출하지 말고 adapter에서 필요한 endpoint만 고정 호출해야 함.

### 4. Financial Datasets MCP: 성숙도는 좋지만 pricing/coverage 확인 전 보류

GitHub maturity는 좋고 재무제표, 가격, 뉴스까지 깔끔해 보임. 하지만 API key와 pricing/무료 범위를 확인해야 하고, KR coverage가 부족할 가능성이 큼. US-only 재무/뉴스 보강용으로는 후보지만, StockInsight의 hard requirement인 Korean data를 해결하지 못함.

### 5. News MCP Server: 아이디어는 좋지만 production source로는 이르다

여러 뉴스 API를 quota 기반으로 전환하는 구조는 좋아 보임. 그러나 저장소가 매우 작고, 각 뉴스 API의 무료 quota/ToS/기사 본문 제공 범위가 다름. KR Naver News를 대체하기는 어려우므로, 현재 `collectors/news.py`를 유지하는 것이 안전함.

### 6. Korea Investment MCP: 이름은 강하지만 즉시 데이터 수집용은 아님

한국투자 API 전체 카테고리를 자연어로 찾는 도구에 가까움. 실제 시세/수급 데이터를 안정적으로 받아 card에 넣으려면 결국 한국투자 API client를 별도로 호출해야 할 수 있음. 즉시 adopt보다는 “추후 KIS API를 직접 붙일 때 문서 검색 도우미” 정도로 보는 것이 맞음.

### 7. yfinance 계열 MCP: 편하지만 단일 truth source로 쓰면 위험

Yahoo Finance MCP는 빠르게 붙이기 좋고 무료라서 매력적임. 하지만 yfinance는 공식 API가 아니므로 구조 변경, 지연 데이터, rate limit 문제를 피하기 어려움. StockInsight card의 deterministic layer에는 DB cache와 fallback이 반드시 필요함.

---

## Section 7 — Open Questions

1. **DartLab의 실제 MCP latency**
   - remote SSE와 local `uv run dartlab mcp` 중 어느 쪽이 빠른지 측정 필요.
   - 카드 생성 p95 10초 내 병렬 fetch에 들어갈 수 있는지 확인 필요.

2. **DartLab의 KR/US ticker mapping**
   - 삼성전자 `005930`, `005930.KS`, corp code, CIK mapping을 얼마나 자동으로 해주는지 확인 필요.
   - 실패 시 내부 ticker mapping table이 필요함.

3. **pykrx-mcp의 투자자 수급 freshness**
   - 외국인/기관 순매수 데이터가 장중/일마감 중 어느 기준인지 확인 필요.
   - KRX 변경 시 장애 가능성도 확인 필요.

4. **Korea Stock MCP의 KRX API 승인과 실제 비용**
   - README상 KRX API key와 승인 절차가 필요함.
   - 개인/비상업용으로 안정적으로 쓸 수 있는지 확인 필요.

5. **SEC EDGAR MCP의 AGPL 영향**
   - 개인용 로컬 사용이면 큰 문제는 없을 수 있으나, StockInsight repo에 서버 코드를 포함하거나 수정 배포할 경우 의무 확인 필요.

6. **FRED MCP 중 어느 구현을 쓸지**
   - Stefano Amorelli 버전은 성숙도와 Docker 배포가 좋아 보이지만 AGPL.
   - cfdude/mcp-fred는 MIT이고 기능이 넓지만 신생 저장소라 안정성 검증 필요.

7. **무료 API quota**
   - Alpha Vantage, Finnhub, FMP, Financial Datasets, NewsAPI.ai, Brave, Exa, Tavily는 무료 quota가 각자 다름.
   - StockInsight는 카드 1개 생성에 여러 fetch가 병렬로 들어가므로, “하루 몇 카드 생성 가능?”으로 환산해야 함.

8. **KR 뉴스 MCP 부재**
   - 이번 조사에서는 Naver News를 안정적으로 대체할 MCP를 찾지 못함.
   - 현재 `collectors/news.py` 유지가 맞고, MCP는 US/global web 보강 정도가 적절함.

9. **관계 그래프 원천**
   - peer/supply chain/theme relation을 무료로 고품질 제공하는 MCP는 뚜렷하지 않음.
   - internal curated relation table, LLM extraction, Exa/Tavily discovery, Graphiti/Neo4j storage를 조합해야 함.

10. **MCP tool 직접 노출 vs adapter 호출**
    - LLM에게 100개 이상의 MCP tools를 그대로 노출하는 것은 비추천.
    - StockInsight backend에서는 `services/external_mcps/` 아래에서 필요한 tool만 deterministic하게 호출하고, LLM에는 정리된 JSON만 넘기는 구조가 안전함.

---

## Suggested Adoption Plan

### Step 1 — Adapter layer 추가

```text
backend/app/services/external_mcps/
  dartlab_adapter.py
  pykrx_adapter.py
  sec_edgar_adapter.py
  fred_adapter.py
  search_adapter.py
```

각 adapter는 MCP 결과를 그대로 노출하지 말고 내부 표준 schema로 변환함.

```python
class FinancialSeries(BaseModel):
    ticker: str
    source: str
    period_type: Literal["annual", "quarterly", "ttm"]
    rows: list[dict]
    fetched_at: datetime
    confidence: float
```

### Step 2 — 기존 collector와 병렬 비교

처음에는 삭제하지 말고 아래처럼 둘 다 호출함.

```python
current_financials = await collectors.financials.fetch(ticker)
mcp_financials = await dartlab_adapter.fetch_financials(ticker)

merged = financial_merge_service.merge(
    current=current_financials,
    mcp=mcp_financials,
    prefer_mcp_for=["income_statement", "balance_sheet", "cash_flow"],
    prefer_current_for=["market_cap", "dividend_yield"],
)
```

### Step 3 — 캐시 정책

- OHLCV: 1일 또는 장중 15분
- 공시 목록: 1시간
- 공시 원문/재무제표: 1일
- FRED macro: 1일
- web/news search: 1시간
- relation discovery: 7일 이상

### Step 4 — 우선순위

1. DartLab financials
2. pykrx investor flow
3. SEC EDGAR insider/Form 4
4. FRED macro
5. Exa/Tavily relation/news discovery

이 순서가 가장 적은 변경으로 카드 품질을 올릴 가능성이 큼.

---

## Source URLs Checked

- DartLab PyPI: https://pypi.org/project/dartlab/
- pykrx-mcp: https://github.com/sharebook-kr/pykrx-mcp
- Korea Stock MCP: https://github.com/jjlabsio/korea-stock-mcp
- DART MCP Server: https://github.com/snaiws/DART-mcp-server
- Korea Investment MCP: https://github.com/koreainvestment/koreainvestment-mcp
- SEC EDGAR MCP: https://github.com/stefanoamorelli/sec-edgar-mcp
- Alpha Vantage MCP: https://github.com/alphavantage/alpha_vantage_mcp
- Yahoo Finance MCP Server: https://github.com/laxmimerit/yahoo-finance-mcp-server
- Yahoo Finance MCP by Alex2Yang97: https://github.com/Alex2Yang97/yahoo-finance-mcp
- FRED MCP Server: https://github.com/stefanoamorelli/fred-mcp-server
- mcp-fred: https://github.com/cfdude/mcp-fred
- Massive MCP: https://github.com/massive-com/mcp_massive
- Polygon MCP fork/reference: https://github.com/ChrisSc/mcp_polygon
- Financial Datasets MCP: https://github.com/financial-datasets/mcp-server
- Financial Modeling Prep MCP: https://github.com/imbenrabi/Financial-Modeling-Prep-MCP-Server
- Finnhub MCP: https://github.com/cfdude/mcp-finnhub
- NewsAPI.ai MCP: https://github.com/eventregistry/newsapi-mcp
- News MCP Server: https://github.com/guangxiangdebizi/news-mcp
- Brave Search MCP: https://github.com/brave/brave-search-mcp-server
- Tavily MCP: https://github.com/tavily-ai/tavily-mcp
- Exa MCP: https://github.com/exa-labs/exa-mcp-server
- Unusual Whales MCP: https://github.com/unusual-whales/unusual-whales-mcp
- StockScreen MCP: https://github.com/twolven/mcp-stockscreen
- Reddit MCP Server: https://github.com/jordanburke/reddit-mcp-server
- Neo4j MCP: https://github.com/neo4j-contrib/mcp-neo4j
- Graphiti MCP: https://github.com/getzep/graphiti
