# MCP Server Survey — Stock Analysis Data Sources

**Purpose:** Brief for another AI to investigate whether existing MCP
(Model Context Protocol) servers could replace or augment large parts of
the custom data-collection backend currently being built for the
StockInsight project.

**Trigger:** While designing a stock-analysis card with custom collectors
for DART filings, news, indicators, macro factors, and ontology relations,
I discovered the **DartLab MCP server** (`pip install dartlab` → `dartlab mcp`),
which exposes Korean DART + US SEC EDGAR filings as tools. This raised the
worry: *am I over-building data infrastructure that already exists as
ready-made MCP servers?* I want a thorough survey before continuing.

---

## 1. Project context

**StockInsight** is a stock-analysis dashboard for personal/family use
(3 users, not a public product). Korean and US stocks. Stack: Next.js 16
+ React 19 frontend, FastAPI + PostgreSQL backend, Azure OpenAI for LLM.

**The differentiating bet** vs. ChatGPT for stock questions:

- Structured analyst card (not chat) with quantitative depth + cited evidence
- Ontology-aware: peer / supply chain / theme / macro relations between stocks
- Buffett-style scenario thinking (BULL/BASE/BEAR with probabilities)
- Layered output: deterministic data (LLM never echoes) + analyst judgment
  (LLM-only, 4 fields: glance / thesis / relations narrative / decision)
- Per-metric Good/Bad labels relative to sector peers (planned)
- Highlight contradictions (e.g., "ROE 25% but debt 200%")
- Stock-universe graph visualization (planned, P3)
- Light chat layer ("ask the card a follow-up") (planned, P4)

**Phasing:**
1. P1 backend engine (refactor just shipped: data layer + analyst LLM split)
2. P2 frontend card (Next.js, 7 sections)
3. P3 stock universe (force-graph 2D)
4. P4 chat evolution (anchored to card)
5. P5 polish

---

## 2. Big-picture features that need data

For each, I'm currently planning to build / am building custom collectors
or LLM tooling. The question for each: **does an MCP server already do
this, well enough, free?**

| # | Feature | Data needed |
|---|---------|-------------|
| 1 | Single-stock card with current price, OHLCV history, indicators (RSI/ATR/MA/RVOL/OBV/CMF) | Daily OHLCV (KR + US), 60–120 days lookback |
| 2 | Fundamentals — PER, PBR, market cap, dividend yield, ROE, plus 5y series for z-scores | Quarterly + annual financials (KR DART, US SEC) |
| 3 | Recent news (≤ 14 days) with title + source + URL + content snippet, classified by topic/sentiment/impact | Korean news (Naver, etc.), US news (NewsAPI / others), categorized |
| 4 | Recent disclosures (DART for KR, SEC for US) — last 30 days | DART filings (8-K equiv), SEC EDGAR filings |
| 5 | Macro context — VIX, US10Y, USD/KRW, sector ETFs (XLK/XLF/XLE), upcoming events (FOMC, earnings calendar) | FRED, market data, economic calendar |
| 6 | Peer / supply-chain / group / theme / macro relations between stocks | Custom AI curation today; Could be replaced if a knowledge graph MCP exists |
| 7 | Investor flow — foreign + institutional net buying (KR-specific) | KRX scrape (no public API I know of) |
| 8 | Stock screener — semantic, e.g., "HBM exposure + ROE improving trend + recent insider buying" | Combined fundamentals + relations + alt-data |
| 9 | Sector-relative metrics (PER 8 vs sector median 12) for Good/Bad labels | Need sector classification + peer data |
| 10 | Insider trades, institutional holdings, analyst estimates / price targets | Currently NOT collected |
| 11 | Social sentiment (Reddit, StockTwits, Korean stock forums) | Currently NOT collected |
| 12 | Earnings calendar with consensus estimates | Currently NOT collected |
| 13 | ETF holdings, fund flows | Currently NOT collected |

Items 10–13 we considered out of scope but would be high-value adds if
free MCP servers exist for them.

---

## 3. Current data pipeline (what we have today)

Built or in-progress in `backend/app/`:

| Layer | What | Implementation status |
|-------|------|------------------------|
| `collectors/stocks.py` | Stock metadata + current price | Built (KR via pykrx-like, US via yfinance-like) |
| `collectors/news.py` | Korean news via Naver | Built |
| `collectors/us_news.py` | US news | Built |
| `collectors/disclosures.py` | DART disclosures | Built (DART_API_KEY required, 10K calls/day limit) |
| `collectors/financials.py` | PER/PBR/시총/배당 only | Built — **shallow**, no historical series |
| `collectors/macro.py` | VIX, US10Y, FX, sector ETFs | Built |
| `collectors/exchange_rates.py` | FX rates | Built |
| `services/analyst/data_layer.py` | Aggregates above into a card | Just shipped (P1 refactor) |
| `services/analyst/tools.py::web_search` | Tavily for analyst LLM | Built — generic web, not finance-specific |
| `services/analyst/indicators.py` | RSI/ATR/MA/RVOL/OBV/CMF — pure Python | Built |
| `services/analyst/tools.py::llm_discover_relations` | LLM curates peer/theme relations | Built — **expensive, hard to verify quality** |

**Where I suspect MCPs could replace or simplify:**

- Item 2 (fundamentals depth) — `dartlab` already does KR + US financials with
  account-name normalization + quarterly cumulative reverse-calc.
  Replacing `collectors/financials.py` would be a major simplification.
- Items 5, 12, 13 — macro / earnings calendar / fund flows. Probably
  many MCP servers exist (FRED, Yahoo Finance, Polygon, etc.).
- Items 10, 11 — insider trades, social sentiment. Likely covered by
  niche MCP servers.
- Item 6 — relations / knowledge graph. Less sure if any MCP covers this.

---

## 4. What I already know about (do not re-research these)

- **DartLab MCP** (`pip install dartlab` → `dartlab mcp`)
  - Korean DART + US SEC EDGAR filings
  - Free, Apache 2.0, OpenDART API key not required for basic use
  - Provides: financial statements (BS/IS/CF), business descriptions,
    risk factors, executive comp, governance, K-IFRS notes
  - Uses official DART API under the hood (10K calls/day limit applies)
  - **Reference, but please find more.**

The whole point of this brief is to find what I *don't* know about.

---

## 5. Research request

You are a research assistant. Investigate and report on **MCP servers
relevant to the data needs in section 2**. The MCP ecosystem is young and
evolving — search GitHub, awesome-mcp lists, the Anthropic MCP registry,
recent blog posts, and Korean sources (since KR data sources may be
underrepresented in English lists).

### Specific tasks

1. **Survey** — find at least 15 MCP servers across the categories below.
   For each, report:
   - Name + repo / homepage URL
   - What data / capabilities it provides
   - License + cost (free / paid / freemium / API key required)
   - KR / US / global coverage
   - Maturity signal (stars, last commit, has releases)
   - Install command (e.g., `pip install`, `npm install`, `npx`, manual)
   - MCP entry point (e.g., `command + args` for `.mcp.json`)
   - Any known limits (rate limit, daily quota)

2. **Categorize** by which feature in section 2 they could serve.

3. **Flag any that could replace large parts of our custom backend** —
   especially `collectors/financials.py`, `collectors/macro.py`, and
   any Phase-A chat tools. Be explicit about the trade-off (MCP coverage
   vs. our existing custom pipeline).

4. **Surface unknown unknowns** — categories I didn't list in section 2
   but that exist as MCP servers and would be high-value for a stock
   analyst card (e.g., options flow, dark pool data, central bank
   speech transcripts, macro forecasts).

5. **Korean-specific search** — since DartLab was found via a Korean
   blog (eddmpython.github.io/dartlab), search for Korean-language MCP
   resources. Check Korean dev blogs, Velog, GitHub Korean accounts.

6. **Recommendation** — pick the top 3–5 MCP servers I should adopt
   immediately (justified by section 2 features), and explain in 1
   paragraph each why.

7. **Anti-recommendation** — if you find MCP servers that look
   appealing but have hidden costs (e.g., scraping ToS issues, abandoned
   project, paywall after free tier, KR-only with no English docs and
   broken install), flag them so I don't waste time.

### Search strategies to use

- "stock MCP server", "finance MCP", "trading MCP", "market data MCP"
- "MCP awesome list", "modelcontextprotocol awesome"
- GitHub search: `topic:mcp finance`, `topic:mcp stocks`, `topic:mcp trading`
- Anthropic's MCP server registry / official directory
- Korean: "한국 주식 MCP", "국내 주식 MCP 서버", "MCP 서버 만들기"
- Specific orgs: bloomberg/refinitiv equivalents, Yahoo Finance,
  Alpha Vantage, Polygon, Finnhub, IEX Cloud, FRED
- News-specific: news API MCPs, Korean news MCPs

### Output format

Markdown document with:

```
# Findings

## Section 1 — Survey
Table of 15+ MCP servers, columns as specified.

## Section 2 — By Feature
For each feature in this brief's section 2, list applicable MCP servers.

## Section 3 — Replace-or-Augment Analysis
"If you adopt X, you can delete/simplify Y in your backend."
Be specific about what code becomes redundant.

## Section 4 — Unknown Unknowns
New categories worth considering.

## Section 5 — Top Recommendations
3–5 must-adopt MCPs with justification.

## Section 6 — Anti-recommendations
Hype traps to avoid.

## Section 7 — Open Questions
Things you couldn't determine that I'd need to verify.
```

Aim for ~2000–3000 words, with concrete URLs, install commands, and
specific code-replacement claims rather than vague recommendations.

---

## 6. Constraints to keep in mind

- **Solo dev + family-of-3 product.** No budget for paid APIs at this
  stage. Free tier or one-time install only.
- **Already committed** to: PostgreSQL + uv (Python), Next.js (TS).
  Backend MCP integration would happen in `services/analyst/data_layer.py`
  or a new `services/external_mcps/` module — not a rewrite.
- **Latency budget:** A single card analysis already takes ~30–60s end
  to end (LLM + tools). New MCP fetches must fit in `asyncio.gather`
  parallel block, ideally < 10s p95 each.
- **Korean data must work.** Many finance MCPs are US-only. KR coverage
  is a hard requirement for at least the financials + news + macro
  layers.
- **Replacing existing collectors only makes sense if** the MCP gives
  noticeably richer data (e.g., 5y financial series vs. our current
  single-period) or better quality (e.g., normalized account names),
  not just a different spelling.

---

## 7. What I'll do with the report

1. Adopt 1–2 immediately to test (next session, post-DartLab evaluation).
2. Decide if any custom collectors should be deleted in favor of MCPs.
3. Update the v2 spec (`docs/superpowers/specs/2026-04-28-...`) to
   reference the chosen MCPs as data sources.
4. Add the chosen MCPs to project `.mcp.json`.

If the report is good, I'll save it as
`docs/research/2026-04-29-mcp-data-source-findings.md` next to this brief.
