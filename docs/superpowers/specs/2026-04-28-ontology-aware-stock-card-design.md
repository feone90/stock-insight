# StockInsight v2 — Ontology-aware Analyst Card

**Status:** Draft — pending user review
**Date:** 2026-04-28
**Author:** brainstorming session (yohan1422@gmail.com + Claude)
**Branch:** `feat/phase-a-tools-expansion` (current) → new branch on plan acceptance

---

## 1. Summary

Pivot StockInsight from a chat-only stock agent (Phase A — shipped, but indistinguishable from ChatGPT) to a **structured single-stock analysis card** powered by an **ontology-aware LLM analyst** with an evidence-first, long-horizon, scenario-based posture.

Each stock gets one card. The card shows a hero price chart, a 3-cell verdict panel (Final Grade / Stance / Entry Stage), a one-line thesis, and seven progressively-disclosable sections (종합 의견, 모멘텀, 관계, 뉴스, 매크로, 펀더멘털, 의사결정). Every numerical claim is cited [n] with a per-section source pool. Each section can drill down into a depth memo (지지근거, 반대근거, catalysts, BULL/BASE/BEAR 시나리오).

The 관계 section opens a dedicated **Stock Universe view** — a 2D galaxy visualization with parallax/glow showing the analyzed stock as a sun, peer/supply/group/theme/macro nodes as orbiting bodies. No competitor (Bloomberg, 토스증권, 네이버증권) ships this.

The engine is a **two-stage agent**: a Research agent with broad tool access (DB queries, indicator computation, dynamic web search, news topic tagging) gathers evidence per analysis request; a Synthesizer LLM with a persona prompt (internal name `analyst_v1`) and Pydantic schema produces the final card. Output structure is enforced; analyst posture is encoded as system prompt rules.

The existing chat agent is repurposed as a **follow-up Q&A panel** anchored to a specific card — not a free-form `/chat` page. The standalone chat surface is removed.

> **UI 카피 룰**: 페르소나 내부 이름 (`analyst_v1`, "Buffett-grade" 식 약어)은 시스템 프롬프트/코드/메모리에만. 사용자 화면에는 절대 노출 X. UI 카피는 **"증거 기반 장기 관점 분석"**, **"균형 잡힌 투자 판단 보조"**, **"시나리오 기반 리스크 해석"** 같은 중립적 표현 사용. 기대치 과장 금지.

---

## 2. Motivation

Phase A shipped a 9-tool chat agent with 95% tool-selection accuracy. Operationally it works. Strategically it fails:

- The user (and family of 3) cannot tell it apart from asking ChatGPT directly.
- It delivers DB facts in natural language. ChatGPT delivers similar quality with broader knowledge.
- It has no relational reasoning (peer/supply/group/theme), no big-picture market context, no forward-looking framing, no structured output, no visual identity.
- The reference vision (GOOG card mockup) is a quant-driven decision support tool — fundamentally different shape.

The user's brief: *"주식 한 종목에 대해 엄청나게 똑똑한 분석. 워렌버핏 같은 전문가의 자세. 단순 정보 전달 X, 부정확 X, 근거 없음 X. 시장 전체 흐름 + 미래 흐름 + 호재/악재 예측 가능. 모든 분석에 근거."*

Differentiation lives in three places:
1. **Ontology layer.** Curated peer/supply/group/theme relations + macro sensitivity, surfaced visually.
2. **Analyst persona.** Evidence rule, balanced theses, scenario sizing, "권한 밖" admission.
3. **Structured output.** Cited claims, drill-down detail, no chat-blob hand-waving.

ChatGPT cannot do (1) or (3). (2) can be approximated but is unprompted by default — owning it is our value.

---

## 3. Product Shape — The Card

### 3.1 Layout

```
┌────────────────────────────────────────────────────┐
│  HEADER                                            │
│   ticker · 한국어이름 · Samsung Electronics · KRX   │
│   [반도체] [AI/HBM] [대형주]                        │
│   ⚠ 관망 — 진입 보류                   ₩78,400    │
│                                       +1,200(+1.6%)│
│                                       2026.04.28  │
├────────────────────────────────────────────────────┤
│  HERO CHART   [1D] [1W] [1M✓] [3M] [1Y]           │
│   ┌─ 종가 line + MA20 dashed + Volume bars ──┐    │
│   │                                          │    │
│   │  (lightweight-charts v5)                 │    │
│   │                                          │    │
│   └──────────────────────────────────────────┘    │
├────────────────────────────────────────────────────┤
│  AT-A-GLANCE                                       │
│   ┌─Final Grade─┐ ┌─Stance───┐ ┌─Entry Stage─┐    │
│   │  C+ ↓B      │ │  관망    │ │  보류        │    │
│   └─────────────┘ └──────────┘ └──────────────┘    │
│   HBM 모멘텀 살아있으나 외국인 4일 순매도 +         │
│   미 10Y 4.6% 부담. 5/7 실적 전 진입 보류. [1][2] │
├────────────────────────────────────────────────────┤
│  SECTIONS (collapsible, progressive disclosure)    │
│   ▣ 종합 의견 (보라 강조, 기본 펼침)              │
│   ▢ 📊 모멘텀 / 기술 (기본 접힘)                  │
│   ▢ 🔗 관계  [그래프로 보기 →]                    │
│   ▢ 📰 뉴스 / 이슈                                 │
│   ▢ 🌐 매크로 / 사회 이슈                          │
│   ▢ 📐 펀더멘털                                    │
│   ▣ ✅ 의사결정 (녹색 강조, 기본 펼침)            │
├────────────────────────────────────────────────────┤
│  FOOTER                                            │
│   ↻ 분석 갱신 2시간 전 · 12개 출처     [강제 갱신] │
│                                       [분석에 질문]│
└────────────────────────────────────────────────────┘
```

### 3.2 Section content

| 섹션 | Compact (1줄) | Expanded (드릴다운) |
|------|----------------|----------------------|
| 종합 의견 | 긍정 N · 반대 N · BASE 시나리오 N% · catalysts N건 (없으면 "임박 일정 없음") | depth memo: thesis, 지지근거(≥3), 반대근거(≥2), 14일 내 catalysts (있을 때만 표시), BULL/BASE/BEAR 시나리오 (확률 + scenario_price) |
| 모멘텀/기술 | 3개 stat tile (RSI, MA stack, RVOL20) | 추가 지표 (MFI, ATR%, CMF, OBV, 박스 위치, 캔들질) + 해석 |
| 관계 | "SK하이닉스 +2.8% / 한미반도체 −1.1% / AI/HBM 테마 +1.2%" + [그래프로 보기→] | peer 강도 비교 표 + 공급망 전후방 + 테마 정렬 + 매크로 β + Stock Universe 뷰 진입 |
| 뉴스/이슈 | "HBM3E 양산(+) · NVIDIA 공급(+) · 환율 부담(−)" | 최근 N일 + 동시대 보도 (catalyst 시점 ±N일), 토픽/감성 태깅, 본문 요약 |
| 매크로/사회 | "VIX 18.7 / USD/KRW 1,378 / 미 10Y 4.6%" | 매크로 팩터별 β, 본 종목 영향 방향, 임박 매크로 일정 (FOMC, 연준 발언, 정책) |
| 펀더멘털 | 3개 stat tile (PER, PBR, 시총) | 5년 평균 대비 z-score, 동종 평균 대비 위치, 배당 이력, 주요 비율 |
| 의사결정 | stance + 기준 지지선 + 시나리오 한 줄 | stance 근거, BULL/BASE/BEAR 확률 + scenario_price, risk_threshold, 추정 손익비, "참고용" 면책 |

### 3.3 Citation pattern

- 모든 numerical claim에 inline `[n]` 배지. **Citation은 데이터 출처 전용** — LLM의 해석은 출처가 아님.
- 클릭 → 같은 섹션 하단 source list로 스크롤 (D4 결정).
- Source list는 섹션별 분리 (전체 합본 출처 풀 X — 섹션 단위 인지 부담 줄임).
- Footer에 합산 N (예: "12개 출처") 표시.

#### 출처 분류 (`source_type`)

| 값 | 설명 |
|----|------|
| `db` | 자체 DB row (분석 시점 스냅샷) |
| `market_data` | 외부 시세 데이터 (yfinance/fdr/KRX 등) |
| `news` | 뉴스 기사 본문 |
| `disclosure` | 공시 (DART/SEC) |
| `web` | 웹 서치 결과 |
| `curated_relation` | AI 큐레이션 관계 데이터 (peer/공급망/테마, 캐시 + TTL) |

#### 해석 분류 (`interpretation`) — 별도 레이어

LLM 해석은 출처가 아니라 해석 레이어. citation에 섞지 않고 audit/eval용 메타데이터로 분리.

| 값 | 설명 |
|----|------|
| `model_generated` | LLM 종합 판단 (thesis, scenario 확률, 정성 해석) |
| `rule_based` | 결정론적 계산 (RSI/MA/β 등 수식) |

해석은 **claim 단위로 라벨**되며, 모든 해석 claim은 자기가 근거한 citation들을 `based_on`으로 명시.

### 3.4 Verdict 척도 (D2)

- **Final Grade**: 5단계 `S / A / B / C / D` (정성 종합 등급, 사이클·구조·실행 종합)
- **Stance**: 3단계 `BUY / WATCH / REJECT` (행동 관점 — 단정 약화 위해 `strategy`에서 rename)
- **Entry Stage**: 3단계 `ENTER / WAIT / REJECT` (진입 적시성)
- 어제 대비 Grade 변화 표시: `C+ ↓ B` (D6 결정 — MVP는 Grade만, sparkline은 v2+)
- "참고용" 라벨 명시 (D5) — 특히 의사결정 섹션. 단정형 어조 회피.

#### 한국어 UI 라벨 매핑

| 내부 enum | 한국어 라벨 |
|-----------|-------------|
| `BUY` | 매수 후보 |
| `WATCH` | 관망 |
| `REJECT` | 보류 |
| `ENTER` | 진입 시점 |
| `WAIT` | 대기 |

---

## 4. Engine Architecture — 2-Stage Agent

### 4.1 흐름도

```
USER click "분석 갱신" (or scheduler tick)
        │
        ▼
┌─────────────────────────────────────────────┐
│  STAGE 1: RESEARCH AGENT                    │
│   - LLM (cheap model: gpt-5-mini-tier)      │
│   - System prompt: "리서처. 증거 수집 자유. │
│     필요한 도구 자유롭게 호출. 5~10 round." │
│   - Tool access: 15+ tools (DB + web + llm) │
│   - Output: free-form research notes JSON  │
│     {findings, citations, gaps_noted}       │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│  STAGE 2: SYNTHESIS AGENT                   │
│   - LLM (premium: gpt-5 / Claude Sonnet 4.6)│
│   - System prompt: analyst_v1 persona +     │
│     evidence rule + balance rule + scenario │
│   - Input: research notes + Pydantic schema │
│   - Output: StockCard (typed, validated)    │
│   - Failure mode: missing fields → fallback │
│     "데이터 부족" markers per section       │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
        DB save to analyses table
        (versioned: persona_v, schema_v, data_v)
                  │
                  ▼
        SSE stream to frontend
        (compact card first, then sections)
```

### 4.2 Why 2-stage

- Single-shot agentic loop (Option A in brainstorm) — LLM does too much at once. Persona consistency drifts as tool calls multiply. Hard to control evidence rigor.
- Multi-agent (Option C — LangGraph specialists) — overengineering for personal scope. Phase B 초기 설계가 이거였다 무거워졌음.
- 2-stage hits the sweet spot: research is exploratory and cheap; synthesis is rigorous and structured.

### 4.3 Round budget

- Research: max 10 tool rounds, max 60s, max ~50K tokens.
- Synthesis: single shot, structured output mode. ~5K tokens.
- Total per analysis: ~$0.5–1.2 cost, ~60–120s wall clock.
- Cooldown per stock: 5min between forced refreshes (rate limit).

### 4.4 Failure modes

- Research timeout → synthesize with partial data, mark missing sections.
- Synthesis schema validation fail → retry once with strict-mode prompt; fail = "분석 생성 실패" banner + last-good cached version.
- Web search 0 results → noted in research output, synthesis section degrades gracefully.
- Tool call error (DB row missing, API 429) → research agent notes gap, continues with available data.

---

## 5. Data Layers — All 10 in Scope

| 레이어 | 출처 | 신선도 | 도구 (Stage 1 expose) |
|--------|------|---------|------------------------|
| 정량 지표 | DB OHLCV → 계산 | 일별 | `get_indicators(ticker)` (RSI, MFI, ATR%, CMF, OBV, MA stack, RVOL, 박스) |
| 뉴스 토픽+감성 | 본문 + LLM 분류 | 일별 (수집 시점) | `get_recent_news`, `get_news_around_date`, `llm_classify_news` |
| Peer / 경쟁사 | LLM curation + 캐시 (7일 TTL) | 7일 | `get_relations(ticker, type="peer")`, `llm_discover_peers(ticker)` |
| 공급망 (전/후방) | LLM curation + 캐시 (14일 TTL) | 14일 | `get_relations(ticker, type="supply")`, `llm_discover_supply(ticker)` |
| 테마 / 내러티브 | LLM curation + 캐시 (7일 TTL) | 7일 | `get_relations(ticker, type="theme")`, `llm_classify_themes(ticker)` |
| 매크로 컨텍스트 | 외부 API (FRED, KRX, FX) | 일별 | `get_macro_context()` (VIX, US10Y, USD/KRW, 섹터 ETF) |
| 사회 이슈 → 종목 매핑 | 동적 web search | 분석 시점 | `web_search(query)`, `web_fetch(url)` — keyword는 LLM이 매번 결정 |
| 과거 유사 패턴 | 백테스트 (deferred to v2.1) | 일별 | `find_similar_patterns(ticker)` — 미구현 (TODO) |
| 수급 (외국인/기관) | KRX 투자자별 (KR 한정) | 일별 | `get_investor_flow(ticker)` (KR only) |
| 모자회사 / 지배구조 | LLM curation + 캐시 (30일 TTL) | 30일 | `get_relations(ticker, type="group")` |

**큐레이션 원칙 (사용자 요구):** 사용자가 직접 정의 X. 모든 관계 데이터는 LLM이 자동 발견 + 캐시. TTL 만료 또는 수동 강제 갱신 시 LLM이 web search로 재조사. 캐시 hit 시 출처에 "AI 큐레이션 (캐시 N일)" 표시.

**동적 web search 원칙:** 키워드 고정 X. 종목/날짜에 따라 LLM이 매번 다른 키워드 결정 (예: 오늘 "트럼프 관세 → 삼성전자", 내일 "미 메모리 자급률 → 삼성전자"). web_search 도구는 query를 LLM에 일임.

---

## 6. Analyst Persona

System prompt에 박아넣을 행동 룰. Stage 2 Synthesizer 전용 (Stage 1은 더 자유로움).

> **이름 정책**: 내부 코드/메모리/시스템 프롬프트에서는 "Buffett-grade", `analyst_v1` 같은 약어를 자유롭게 사용해도 됨 (개발자에게 의미 전달용). 단, **사용자 화면, 마케팅 카피, 에러 메시지, 챗 응답에는 절대 노출 금지**. 기대치 과장 회피.

### 6.1 양성 룰 (DO)

- **증거 규율**: 모든 수치 클레임에 [n] citation. 출처 없는 수치는 클레임 금지. citation은 데이터 출처만 (LLM 해석은 citation 아님).
- **데이터 vs 해석 분리**: "RSI 58이다" → 데이터 claim ([1] = `db`). "RSI 58은 단기 이격 부담" → 해석 claim (`interpretation: model_generated`, `based_on: [1]`). 두 layer 명확 분리.
- **시장 전체 컨텍스트**: 단일 종목 보지 않음. peer + 섹터 + 매크로 + 사이클 위치 함께 평가.
- **흐름 사고**: 현재 상태만 X. "어디서 왔고 어디로 갈 가능성"을 사이클 관점에서.
- **미래 일정 + 시나리오**: catalysts 있으면 표시, 없으면 **"확인된 임박 일정 없음"** 명시. 억지로 찾지 말 것 (hallucination 위험). bull/base/bear 시나리오 확률은 항상 명시 (예: 25/55/20).
- **반대 근거 의무**: 지지 근거만 나열 금지. 반대 근거 최소 2개 (편향 방지).
- **리스크 인식**: 매수 후보 stance에서 손실 시나리오 + risk_threshold 동시 제시.
- **권한 밖 영역**: 정치 정책 디테일, 기술 미세 디테일 등 권한 밖이면 "데이터 부족" 명시.

### 6.2 음성 룰 (DON'T)

- "좋은 종목입니다", "강력 추천", "유망함" 류 단정형 형용사 → 금지. 수치 + 비교로 대체.
- 사용자에게 아첨 ("좋은 질문") → 금지. 곧장 분석.
- 섹션 채우기용 추측 → 금지. 데이터 없으면 "이 영역 데이터 부족 — 외부 리서치 시도 [세부 사항]" 명시.
- 출처 없는 예측 → 금지. catalyst 추정도 "추정 — 확정 X" 라벨.
- "ChatGPT처럼" 일반 시장 지식만 나열 → 금지. 이 종목 + 이 시점 + 이 데이터에 특화된 분석만.

### 6.3 Persona 버저닝

- 시스템 프롬프트는 `app/services/analyst/persona.py`에 `PERSONA_V1` 상수로 (내부 이름: `analyst_v1`).
- 분석 결과 저장 시 `persona_version` 필드에 같이 저장 — eval 진화 시 어떤 persona가 어떤 출력 냈는지 추적.
- A/B 테스트 가능 (persona_v1 vs persona_v2 결과 비교).

### 6.4 사용자 화면 카피 가이드

내부 페르소나 이름을 UI에 노출하지 말 것. 대신 다음 중립 문구 사용:

| 위치 | 추천 카피 |
|------|-----------|
| 카드 종합의견 라벨 | **"증거 기반 장기 관점 분석"** |
| Onboarding/About 페이지 | **"균형 잡힌 투자 판단 보조 — 시나리오 기반 리스크 해석"** |
| 챗 패널 placeholder | "이 분석에 대해 질문하세요" |
| 분석 진행 중 로딩 | "데이터 수집 + 검토 중..." |
| 면책 (footer) | "참고용 — 투자 권유 아님. 본 분석은 자동화된 판단 보조 도구입니다." |

**금지 표현**: "워렌버핏", "Buffett", "전문가급", "AI가 추천", "강력 매수", "확실한 수익", "유망주". 이런 단어는 spec/코드/UI 어디에도 X (단 내부 변수명 `analyst_v1`, persona prompt 내부는 OK).

---

## 7. Refresh Policy (D1 확정)

| 시장 | 시점 | 시각 (KST) | 내용 |
|------|------|------------|------|
| KR | 장 시작 30분 전 | 매일 08:30 | 전일 미국장 + 야간 뉴스 + 환율 반영. 즐겨찾기 KR 종목 분석 |
| KR | 장 마감 30분 후 | 매일 16:00 | 국내 장 마감 + 외국인/기관 잠정 매매 반영 |
| US | 정규장 종료 후 | 매일 07:00 (= 18:00 ET) | 미국 정규장 가격 확정 + AH 뉴스 |
| US | 정규장 시작 후 | 매일 22:30 (= 09:30 ET) | 프리마켓 movers — 한국 저녁에 새 진입 가능 |
| 전체 | 강제 갱신 | 상시 (5분 cooldown) | 사용자 클릭. LLM 비용 보호로 종목별 5분 룩 |

- 즐겨찾기 종목만 자동 분석 (스케줄러).
- 비-즐겨찾기 종목: on-demand 분석 (사용자 클릭 시 카드 진입 → 분석 트리거 → 24시간 캐시).
- 분석 결과는 `analyses` 테이블 reuse (현 Phase A 사용 중) + 새 컬럼들 추가 (스키마 변경 필요).

---

## 8. Output Schema — Pydantic

```python
# app/schemas/card.py (new)

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

# === Citation = data source 전용. LLM 해석은 출처 아님. ===
SourceType = Literal[
    "db",
    "market_data",
    "news",
    "disclosure",
    "web",
    "curated_relation",
]
InterpretationKind = Literal["model_generated", "rule_based"]

class Citation(BaseModel):
    id: int  # [1], [2], ...
    source_type: SourceType
    label: str  # "DB · 가격 (2026-04-28)"
    url: str | None = None
    timestamp: datetime | None = None

class Interpretation(BaseModel):
    """해석 레이어 — citation과 별도. claim이 어떻게 derived 됐는지 명시."""
    kind: InterpretationKind
    based_on: list[int]  # 어떤 citation들을 근거로 했는지
    rationale: str | None = None  # 짧은 추론 메모 (eval/audit용)

class Claim(BaseModel):
    """수치/정성 주장 1개 단위. data citation + 해석 레이어 분리."""
    text: str  # 본문 ("외국인 4일 연속 순매도")
    citations: list[int]  # 데이터 근거
    interpretation: Interpretation | None = None  # None = 순수 데이터, 있으면 해석

class GlanceVerdict(BaseModel):
    final_grade: Literal["S", "A", "B", "C", "D"]
    grade_delta: Literal["up", "down", "same"] | None = None
    stance: Literal["BUY", "WATCH", "REJECT"]  # renamed from `strategy`
    entry_stage: Literal["ENTER", "WAIT", "REJECT"]
    one_line: str  # 1~2 문장 thesis 요약
    citations: list[int]

class TechMomentum(BaseModel):
    rsi_14: float | None
    mfi_14: float | None
    atr_pct: float | None
    cmf_20: float | None
    obv_ratio: float | None
    ma_stack: Literal["정배열", "역배열", "혼조"] | None
    rvol_20: float | None
    box_position: str | None  # "박스 상단 저항"
    summary_line: str
    citations: list[int]
    interpretation: Interpretation | None = None  # 보통 rule_based + 일부 model_generated

class Relation(BaseModel):
    target_ticker: str
    target_name: str
    relation_type: Literal["peer", "supply_upstream", "supply_downstream", "group", "theme", "macro"]
    strength: float = Field(..., ge=0, le=1)  # correlation or curated weight
    today_change_pct: float | None = None
    notes: str | None = None
    citation_ids: list[int]

class RelationsSummary(BaseModel):
    one_line: str
    relations: list[Relation]
    citations: list[int]

class NewsItem(BaseModel):
    title: str
    source: str
    url: str
    published_at: datetime
    impact: Literal["positive", "negative", "mixed", "neutral"]
    summary: str
    citation_id: int

class MacroSensitivity(BaseModel):
    factor: str  # "USD/KRW", "US10Y", "VIX"
    beta: float  # rule_based 회귀 추정
    direction: Literal["positive", "negative", "neutral"]

class MacroContext(BaseModel):
    one_line: str
    vix: float | None
    fx_pairs: dict[str, float]
    us_10y: float | None
    sensitivities: list[MacroSensitivity]
    upcoming_events: list[str]  # "5/14 FOMC". 빈 리스트 가능
    citations: list[int]

class Fundamentals(BaseModel):
    per: float | None
    pbr: float | None
    market_cap_krw: float | None
    dividend_yield: float | None
    per_5y_z: float | None
    citations: list[int]

class Catalyst(BaseModel):
    when: str  # "5/7 (목)" or "5월 중"
    event: str
    impact_estimate: str  # "±5%" or "−2~3%"
    direction: Literal["positive", "negative", "mixed"]
    citation_ids: list[int]

class Scenario(BaseModel):
    name: Literal["BULL", "BASE", "BEAR"]
    probability: float = Field(..., ge=0, le=1)
    scenario_price: float | None  # renamed from `target_price`
    scenario_change_pct: float | None  # renamed from `target_change_pct`
    rationale: str

class Thesis(BaseModel):
    core_thesis: str  # 핵심 명제 1~2 문장
    supports: list[Claim]  # ≥3
    opposes: list[Claim]  # ≥2
    catalysts: list[Catalyst]  # 빈 리스트 가능 — UI는 "확인된 임박 일정 없음" 표시
    no_catalysts_reason: str | None = None  # catalysts가 비어있을 때 부재 사유 (옵션)
    scenarios: list[Scenario]  # length 3 (BULL/BASE/BEAR), 항상 채움
    citations: list[int]

class Decision(BaseModel):
    stance: Literal["BUY", "WATCH", "REJECT"]  # renamed from `strategy`
    sizing_note: str  # "기본 비중", "대기", "축소"
    support_price: float | None  # 기준 지지선
    risk_threshold: float | None  # renamed from `stop_loss`
    note: str = "참고용 — 투자 권유 아님"
    citations: list[int]
    interpretation: Interpretation | None = None  # 거의 항상 model_generated

class StockCard(BaseModel):
    # Identity
    ticker: str
    name_ko: str
    name_en: str
    market: str
    sector: str
    tags: list[str]

    # Price
    price: float
    change: float
    change_pct: float
    asof: datetime

    # Sections
    glance: GlanceVerdict
    thesis: Thesis  # "종합 의견" 펼친 본문
    technical: TechMomentum
    relations: RelationsSummary
    news: list[NewsItem]
    macro: MacroContext
    fundamentals: Fundamentals
    decision: Decision

    # Citations (모든 [n]의 풀)
    citations: list[Citation]

    # Meta
    analysis_id: str
    generated_at: datetime
    persona_version: str  # 내부: "analyst_v1" 등
    schema_version: str = "v1"
    refresh_state: Literal["fresh", "stale", "loading", "error"] = "fresh"
```

---

## 9. Stock Universe — Ontology Graph (Y option)

### 9.1 진입점

- 카드의 "🔗 관계" 섹션 expanded view 하단에 **"🌐 그래프로 보기"** 버튼.
- 클릭 → 풀스크린 모달 (새 라우트 추가 X — URL 유지, 모바일 친화).
- 모달 내 "🚀 워프" 버튼 = 노드 클릭 시 그 종목 카드로 라우팅 (`/stock/{ticker}`).

### 9.2 시각 메타포 매핑

| 개념 | 시각 표현 | 인코딩 |
|------|-----------|--------|
| 종목 | 별 (star) | 크기 ∝ 시총, 색상 = 오늘 등락률 (green/red), 광도 = 거래량 |
| 분석 대상 | 중심 항성 (sun) | 코로나 + 광선 + pulse 애니메이션, 가장 큰 발광 |
| peer 동조 | 파란 광선 연결 | 두께 ∝ 상관계수 ρ, 거리 ∝ 1/ρ |
| 공급망 | 주황 흐름 입자 | 방향성 (입자 흐름), upstream→downstream 명확 |
| 그룹사 | 보라 결속선 | 가까운 별자리 묶음 |
| 테마 | 성운 (nebula) | 큰 반투명 클라우드, 멤버 종목 그 안에 위치 |
| 매크로 | 우주 배경 색조 | risk-off → 붉은 톤, risk-on → 푸른 톤. β 라벨 |
| 임박 catalyst | 유성 (shooting star) | 단기 이벤트 일회성 빛줄기 |

### 9.3 인터랙션

- 노드 클릭 → 그 종목 카드로 이동 ("워프" 트랜지션).
- 엣지 hover → 관계 메타데이터 (ρ, 마지막 갱신, 캐시 출처).
- 사이드 패널: 관계 타입 5종 토글, 깊이 (1-hop / 1+2 / 3-hop), 시점 (오늘 / 7일 / 30일).
- 카메라: 자동 회전 토글, 초기 위치 복귀, 2D 뷰 토글.

### 9.4 기술 스택

- 베이스: `react-force-graph-2d` — force simulation 빌트인, Canvas 렌더 (50+ 노드 성능 OK).
- 커스텀 렌더 hook으로 글로우/펄스/성운 효과 추가 (`nodeCanvasObject` prop 사용).
- 애니메이션: requestAnimationFrame (그래프 라이브러리 내장) + CSS keyframes (모달 진입/exit).
- 패럴랙스: 카메라 위치 변경 시 배경 별필드를 다른 속도로 이동 (CSS transform).
- 모바일: 1-hop만 표시 (자동 깊이 제한), 풀스크린 모달, pinch-zoom 활성.

### 9.5 데이터 소스

- `stock_relations` 테이블 (새로 추가) 쿼리.
- 시점별 가격은 `price_history` 조인.
- 매크로 데이터는 `macro_factors` 테이블 (새로 추가).

---

## 10. Chat Agent — Evolve to Follow-up (C option)

### 10.1 변경

- `/chat` 페이지 제거 (top-nav "Ask AI" 링크 제거).
- 카드 footer에 **"💬 분석에 질문"** 버튼 추가.
- 클릭 → 카드 하단 슬라이드-업 챗 패널 (모바일/데스크톱 동일 패턴, 카드 컨텍스트 위에 머묾).
- 챗 컨텍스트: 현재 종목 카드 + 분석 결과 + 출처 풀 자동 주입.
- 종료/접기: ESC, 외부 클릭, 또는 패널 헤더 X.

### 10.2 Tool 축소

기존 9개 → 4개 (현재 종목 한정):

| Tool | 용도 |
|------|------|
| `get_section_detail(section)` | "관계" 섹션 raw 데이터 deeper dive |
| `get_citation_source(n)` | [n] 출처 원문/raw 확인 |
| `verify_scenario(name)` | bull/base/bear 시나리오 가정 + 데이터 재검증 |
| `web_search_focused(query)` | 종목명 자동 prefix, 사용자 질문 보강 |

### 10.3 인프라 재활용

- `chat_messages` 테이블: 그대로. `thread_id` + `stock_ticker` 컬럼 추가 (anchor).
- `AzureOpenAIAdapter.chat_with_tools`: 그대로.
- SSE 스트리밍 오케스트레이터: 그대로 (`app/services/chat/stream.py`).
- 시스템 프롬프트만 변경 — `analyst_v1` persona 동일 + "현재 카드 컨텍스트 안에서만 답변. 다른 종목 질문은 거절."

### 10.4 제거

- `/chat` 페이지 (`frontend/src/app/chat/page.tsx`).
- ChatSidebar (스레드 목록 — 현재 anchor가 카드라 불필요).
- 9개 → 4개로 도구 축소 (미사용 도구는 삭제).

---

## 11. State Coverage

| 상태 | 전체 카드 | 개별 섹션 |
|------|-----------|-----------|
| Loading | 스켈레톤 카드 + "분석 중..." + 진행 로그 (Perplexity-style live updates) | 섹션별 스켈레톤 |
| Empty (data) | "이 종목은 분석 데이터 부족" + 수집 시작 버튼 | 섹션 유지, 본문 "데이터 부족 — 외부 리서치 진행 중" |
| Error | 마지막 성공 분석 표시 + 빨간 배너 "최근 분석 실패 — 재시도" | 섹션별 "분석 실패 — 재시도" 인라인 버튼 |
| Stale | 상단 노란 배너 "분석 N시간 지남 — 갱신" | 시각 dim 처리 옵션 |
| Partial | 가능한 섹션만 렌더, 실패 섹션 collapse + 표시 | 미수집 섹션 명시 |
| First-time (종목 신규) | "이 종목 처음입니다 — 데이터 수집 + 분석 (~2분)" + 진행률 | N/A (전체가 first-time) |

---

## 12. Theme System

### 12.1 토큰

- `frontend/src/lib/design-tokens.ts` (새 파일) — light/dark 양쪽 매핑.
- 카테고리: `verdict` (BUY/WATCH/REJECT), `grade` (S/A/B/C/D), `surface` (card/section/glance), `cite` (bg/fg), `chart` (line/area/MA/volume), `relation` (peer/supply/group/theme/macro).
- Tailwind dark: variant + CSS custom properties로 실현.

### 12.2 모드 전환

- 시스템 OS `prefers-color-scheme` 자동 따라가기.
- 수동 토글 — top-nav에 ☀/🌙 버튼.
- 사용자 선호 localStorage 저장.

### 12.3 차트 토큰 (lightweight-charts v5 적용)

- Light: 종가 `#0a8f3d`, MA20 `#a06800`, volume up `#a8d8b8`, grid `#ececef`
- Dark: 종가 `#4ade80`, MA20 `#fbbf24`, volume up `#1f4a2c`, grid `#1a1a22`

---

## 13. Eval Framework

Phase A는 "tool-selection accuracy" eval만 있었음 (19/20 PASS). v2는 분석가 품질 eval 필요.

### 13.1 자동화 가능한 eval

1. **Hallucination check** — 출력 numerical claim 정규식 추출 → citation source (`db/market_data/news/disclosure/web/curated_relation`) 데이터와 매칭. LLM 해석 (`interpretation.kind`)은 별도 분류, 매칭 대상 X. 매칭 실패 = FAIL.
2. **Citation accuracy** — `[n]` 인용이 실제 그 claim을 지지하는가? LLM-as-judge (별도 호출).
3. **Evidence balance** — 지지 근거 ≥3, 반대 근거 ≥2, 시나리오 3개. 구조 체크.
4. **Catalyst handling** — catalysts 있으면 14일 내 ≥1 표시 + 모두 citation 보유. **없으면 `no_catalysts_reason` 또는 명시적 빈 리스트 + UI "확인된 임박 일정 없음" 렌더 — 강제 fabricate 시 FAIL.**
5. **Specificity** — "좋다/나쁘다", "유망", "추천" 같은 단정/형용사 카운트. 정규식. 임계 초과 시 WARN. 금지어 ("워렌버핏", "전문가급", "강력 매수") 등장 시 FAIL.
6. **Interpretation discipline** — `interpretation.kind` 라벨이 있는 claim은 `based_on` citation을 가진다. 해석 claim에 citation 0개 = FAIL.

### 13.2 수동/세미 자동 eval

7. **Cycle awareness** — 사이클 위치 (도입/성장/성숙) 언급 여부. LLM-as-judge.
8. **Cross-stock consistency** — 같은 섹터 두 종목 분석 시 매크로 해석 일치. cross-eval.

### 13.3 Eval harness

- `backend/scripts/eval_card_quality.py` (새 파일).
- 골든 데이터셋: 10~20 종목 (KR/US 혼합) 분석 결과 + 사람 검토 라벨.
- CI 또는 PR에서 자동 실행.

---

## 14. Decisions Log

| ID | 결정 | 확정안 |
|----|------|--------|
| D1 | Refresh 모델 | KR 08:30/16:00, US 07:00/22:30 KST + 강제 갱신 5분 cooldown |
| D2 | Grade 척도 | Final Grade S/A/B/C/D + Stance BUY/WATCH/REJECT (`strategy` → `stance` rename) |
| D3 | 초기 펼침 상태 | 종합의견 + 의사결정만 펼침 (나머지 접힘) |
| D4 | 출처 [n] 인터랙션 | 클릭 → 섹션 하단 source list 스크롤 |
| D5 | 가격/리스크 표현 | "참고용" 라벨 + 단정 약화 어휘: `target_price → scenario_price`, `stop_loss → risk_threshold` |
| D6 | 이력/변화 표시 | MVP는 어제 vs 오늘 Grade ↑↓만. sparkline은 v2.1+ |
| D7 | 데이터 부족 종목 | 부족한 섹션만 "데이터 부족" graceful degradation |
| ARCH | 엔진 아키텍처 | 2-stage (Research → Synthesize) |
| VIZ | 온톨로지 그래프 | Y (2D Galaxy + parallax/glow) — Z 업그레이드는 v2.1 옵션 |
| CHAT | 챗 에이전트 거취 | C (Evolve to follow-up) — `/chat` 제거, 카드 anchor 챗 |
| THEME | 테마 | 다크 메인 + 라이트 토글 (시스템 OS 자동) |
| PERSONA | 분석가 자세 | 내부 이름 `analyst_v1` — 증거 규율, 반대 근거 의무, 시나리오 3개, 권한 밖 명시. **UI 카피는 중립적 표현 (§6.4)** |
| CITATION | 출처/해석 분리 | citation = data source 전용 (`db/market_data/news/disclosure/web/curated_relation`). 해석은 별도 `interpretation` 필드 (`model_generated`/`rule_based`) |
| CATALYST | catalyst 처리 | 14일 내 있으면 표시, 없으면 "확인된 임박 일정 없음" 명시. 강제 find 금지 |

---

## 15. NOT in Scope (Deferred)

- **과거 유사 패턴 백테스트** (10번째 데이터 레이어) — v2.1로 이연. 별도 파이프라인 필요 (1~2주).
- **3D Stock Universe (Z option)** — v2.1+ 옵션. Y 출시 후 사용자 반응 보고 결정.
- **모바일 그래프 풀 인터랙션** — MVP는 1-hop + 모달, 2-hop 인터랙션은 v2.1.
- **자동화된 LLM-as-judge eval (cycle awareness, cross-consistency)** — v2.1. MVP는 hallucination + structure check만.
- **개인화/투자 성향 학습** (Phase D) — 미정.
- **실시간 가격 (WebSocket)** (Phase C) — 미정. 현재 일별 OHLC로 충분.
- **다른 자산군 (채권/암호화폐/원자재)** — 미정.
- **포트폴리오 뷰 (즐겨찾기 종목 묶음 분석)** — v2.1+.
- **이력 비교** ("어제 BUY → 오늘 WATCH 왜?") — v2.1+. MVP는 Grade ↑↓만.
- **수동 큐레이션 UI** (사용자가 peer 직접 추가) — 사용자 명시 거부, 영구 deferred.

---

## 16. What Already Exists (재활용)

### Backend
- `backend/app/services/llm/adapter.py` — `AzureOpenAIAdapter.chat_with_tools` (Phase A에서 검증)
- `backend/app/services/chat/stream.py` — SSE 스트리밍 오케스트레이터, tool-calling loop
- `backend/app/services/chat/tools.py` — 9개 tools (4개로 축소 + 새 tools 추가)
- `backend/app/models/analysis.py` — analyses 테이블 (스키마 확장 필요)
- `backend/app/models/news.py`, `disclosure.py`, `financial.py`, `price.py` — 그대로
- `backend/app/collectors/*` — 그대로 (price, news, financials, disclosure, exchange_rate, scraper)
- `backend/app/scheduler.py` — KR/US 분리 스케줄로 확장
- `backend/scripts/eval_chat_tools.py` — 참고용 (새 eval은 별도)

### Frontend
- `frontend/src/components/stock/*` — 차트 컴포넌트 (lightweight-charts v5) 재사용
- `frontend/src/services/api.ts` — API 클라이언트 패턴
- `frontend/src/services/auth.ts` — JWT
- `frontend/src/components/ui/*` — shadcn/ui primitives

### 인프라
- PostgreSQL 17 + Alembic
- APScheduler
- JWT auth
- 즐겨찾기 시스템

---

## 17. Risks & Unknowns

| 리스크 | 영향 | 대응 |
|--------|------|------|
| Azure OpenAI Responses API가 structured output 미지원 시 | Stage 2 schema 강제 어려움 | smoke test 먼저. 안 되면 JSON parsing + retry loop. |
| Web search API 비용 | 분석 1건 비용 상한 초과 | Tavily Free tier 또는 Bing Free 사용. 비용 budget 모니터링. |
| Peer/공급망 LLM 큐레이션 정확도 | 잘못된 관계로 오분석 | 분석 결과에 "AI 큐레이션 (캐시 N일)" 출처 표시 → 사용자 검증 가능. 명백한 오류는 manual override 가능 (수동 큐레이션 UI 없음 결정과 충돌 — 별도 admin tool 고려). |
| Stock Universe 모바일 성능 | 가족 중 모바일 사용자 경험 저하 | 1-hop 제한 + Canvas 렌더 + 노드 50개 한도. |
| 분석 비용 폭증 | 가족 4명 × 즐겨찾기 5종목 × 1일 2회 (시장별) = 40 분석/day. 단순 곱셈 시 $40/day = $1200/month — personal scope 초과 | **(1) 종목 dedup**: 4명이 같은 종목 즐겨찾기 시 1번만 분석 (예상 unique ~10종목/day). **(2) Stage 분리 비용**: research = gpt-5-mini 등 cheap (~$0.15), synthesis = premium (~$0.10) → 분석당 $0.25 평균. **(3) 하루 분석 cap**: 종목당 자동 갱신 1일 2회 + 강제 갱신 5분 cooldown. **(4) 추정 cost**: 10 unique × 2회 × $0.25 = **$5/day = $150/month**. 가족 4명용 personal에서 수용 가능 범위. **(5) 비상 kill switch**: 일 비용 $10 초과 시 스케줄러 자동 정지 + 알림. |
| 한국어 종목 검색 (Phase A 알려진 한계) | 사용자가 "네이버" 검색 시 NAVER 영문 매핑 실패 가능 | seed에 한국어 alias 컬럼 추가 (TODOS.md 기존 항목). MVP에 포함. |
| `analyses` 테이블 스키마 마이그레이션 | 기존 Phase A 분석 결과와 충돌 | 새 컬럼은 nullable로 추가. 기존 row는 v1으로 라벨링. 새 분석부터 v2 schema. |

---

## 18. Acceptance Criteria

MVP가 "Done"이라 부를 수 있으려면:

- [ ] 즐겨찾기 KR 종목 1개 분석 시 7개 섹션 모두 채워짐 (또는 명시적 "데이터 부족")
- [ ] 즐겨찾기 US 종목 1개 동일
- [ ] 모든 numerical claim에 [n] 인용 + 출처 풀 매칭 — citation은 data source 전용 (`db/market_data/news/disclosure/web/curated_relation`)
- [ ] hallucination check 통과 (출력 수치가 출처 데이터에 실제 존재)
- [ ] 해석 claim은 `interpretation.kind` 라벨 + `based_on` citation 보유
- [ ] 지지근거 ≥3, 반대근거 ≥2, 시나리오 3개 (BULL/BASE/BEAR) 갖춤
- [ ] 14일 내 catalyst 있으면 표시, 없으면 명시적 "확인된 임박 일정 없음" 렌더 (강제 fabricate 시 fail)
- [ ] Stock Universe 뷰에서 노드 ≥4개, 엣지 ≥3 종류 표시
- [ ] 노드 클릭 시 해당 종목 카드로 이동
- [ ] 라이트 + 다크 토글 양쪽 정상 렌더
- [ ] 카드 footer "분석에 질문" → 챗 패널 진입, 컨텍스트 자동 주입
- [ ] KR 스케줄 (08:30/16:00) + US 스케줄 (07:00/22:30) 자동 갱신
- [ ] 강제 갱신 버튼 cooldown 5분 작동
- [ ] 분석 실패 시 stale data fallback + 빨간 배너
- [ ] 모바일 (375px) 카드 정상 렌더, Stock Universe 1-hop 모달 작동
- [ ] eval harness `eval_card_quality.py` 실행 가능, hallucination + 금지어 + catalyst-handling check 자동
- [ ] `/chat` 페이지 제거됨, top-nav에서 안 보임
- [ ] Phase A 분석 결과 (`analyses` 테이블)와 v2 결과 공존 가능 (schema_version 분기)
- [ ] UI 카피에 "워렌버핏", "전문가급", "강력 매수", "확실한 수익" 등 금지어 0건 (정규식 검증)

---

## 19. Implementation Phasing (writing-plans 스킬 가이드용)

전체 spec을 한 번에 구현하면 ~5–6주. 다음 phase로 분해 권장:

| Phase | 내용 | 예상 작업량 | 의존성 |
|-------|------|-------------|--------|
| **P1: Backend Engine** | 2-stage agent + StockCard 스키마 + 신규 tools (indicators/relations/web_search/macro) + persona + analysis API + DB schema 확장 + dedup 로직 | ~2주 | — |
| **P2: Frontend Card** | 카드 컴포넌트 + 7섹션 + 한눈 패널 + hero chart + 라이트/다크 토큰 + 상태 (loading/empty/error/stale) + 기존 chart 재사용 | ~1.5주 | P1 (분석 API 필요) |
| **P3: Stock Universe (Y)** | `react-force-graph-2d` + 글로우/펄스/성운 + 풀스크린 모달 + 워프 라우팅 + 모바일 1-hop fallback | ~1주 | P2 (카드 진입점 필요) |
| **P4: Chat Evolution (C)** | `/chat` 제거 + 카드 anchor 챗 패널 + tool 9개 → 4개 축소 + 슬라이드-업 UI | ~3일 | P2 |
| **P5: Polish + Eval** | KR/US 분리 스케줄러 + 강제 갱신 cooldown + 비용 kill switch + eval harness (`eval_card_quality.py`) + 한국어 alias + Phase A 결과 마이그레이션 | ~1주 | P1, P2 |

**MVP 정의**: P1 + P2 만으로도 카드 자체는 작동. P3 (Stock Universe)는 차별점 핵심이라 MVP에 포함 권장. P4 (Chat)와 P5 (Polish)는 MVP+1.

**제안 순서**: P1 → P2 → P3 → P5 → P4 (Polish가 Chat보다 운영 안정성에 더 중요).

**MVP cut 후 release 시점**: 가족에게 한 종목 (예: 삼성전자) 보여주고 피드백 받기 → P5 후속 작업 결정.

---

## 20. References

- 브레인스토밍 비주얼 산출물 (브라우저 mockup):
  - `01-gap.html` — 현재 vs 목표 갭
  - `04-card-mockup.html` — v1 카드 (라이트, 7섹션)
  - `06-card-v2.html` — v2 카드 (다크 + 한눈 패널)
  - `07-analyst-grade.html` — Buffett-grade 메모 구조 + persona
  - `09-card-big.html` — 풀사이즈 라이트+다크
  - `11-card-with-chart.html` — 메인 차트 hero 적용 (FINAL 카드)
  - `12-stock-universe.html` — Stock Universe 메타포 정리
  - `13-three-options.html` — X/Y/Z 비교 (Y 채택)
- 참고 이미지: GOOG 종목 카드 (사용자 제공) — Final Grade / Strategy / Entry Stage 패턴
- 기존 코드:
  - `backend/app/services/chat/` — Phase A 챗 에이전트
  - `frontend/src/app/chat/` — 제거 대상
  - `docs/superpowers/plans/2026-04-16-phase-a-chat-agent.md` — Phase A 원본 plan

---

## 21. Next Step

이 spec 사용자 승인 → git commit → `superpowers:writing-plans` 스킬로 구현 계획 작성.

구현 계획은 별도 문서: `docs/superpowers/plans/2026-04-28-ontology-aware-stock-card-implementation.md`
