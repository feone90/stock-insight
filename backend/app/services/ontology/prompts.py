"""LLM extraction prompts — DART / SEC / news / web.

Each prompt is a Python format string. `{body}` placeholder is the raw text;
extractor concatenates the schema reminder before sending. Output is a bare
JSON array; `ExtractionBatch.relations` parses both array and `{relations:...}`.

Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §6
Plan: docs/superpowers/plans/2026-04-30-p1.6-relation-extraction.md §6.2~6.4
"""

# v1 — KR DART contract disclosures (단일판매·공급계약 / 주요공급계약).
DART_CONTRACT_PROMPT = """다음은 한국 DART 공시 본문이다. 두 상장사 사이의 명시적 공급/구매 계약을 추출하라.

본문:
{body}

응답 JSON 객체 (자연어 설명 X). `relations` 키 안에 배열을 넣어라:
{{
  "relations": [
    {{
      "from_ticker": "공급자/판매자 종목코드 (KR 6자리 또는 US ticker)",
      "to_ticker": "고객/구매자 종목코드",
      "relation_type": "contract_supplier",
      "signal_direction": "positive",
      "strength": 0.0~1.0,
      "confidence": 0.0~1.0,
      "valid_from": "YYYY-MM-DD" 또는 null,
      "valid_until": "YYYY-MM-DD" 또는 null,
      "metadata": {{
        "value_krw": 계약금액 KRW (숫자, 모르면 null),
        "term_months": 계약 기간 개월수 (모르면 null),
        "rationale": "근거 한 줄"
      }}
    }}
  ]
}}

규칙:
- ticker는 공시에 명시된 6자리 종목코드 또는 US ticker만. 추정 X
- 상대방이 비상장사이거나 외국계 비상장이면 응답에서 제외
- 본문에 액수 명시 없으면 metadata.value_krw=null
- 1개 공시에서 여러 pair 가능. 명시적 계약이 없으면 `relations: []` 빈 배열 반환
- 응답은 위 JSON 객체 1개만"""


# v2 — US SEC 8-K Item 1.01 (Material Definitive Agreement) contract.
SEC_8K_CONTRACT_PROMPT = """The following is a US SEC 8-K filing. Extract any explicit contractual relationship between two publicly listed companies.

Filing body:
{body}

Respond with a single JSON object (no prose, no code fences). Wrap the array in a `relations` key:
{{
  "relations": [
    {{
      "from_ticker": "supplier / seller ticker (US 1-5 letters or KR 6-digit)",
      "to_ticker": "customer / buyer ticker",
      "relation_type": "contract_supplier",
      "signal_direction": "positive",
      "strength": 0.0~1.0,
      "confidence": 0.0~1.0,
      "valid_from": "YYYY-MM-DD" or null,
      "valid_until": "YYYY-MM-DD" or null,
      "metadata": {{
        "value_usd": numeric USD amount (null if not stated),
        "term_months": contract term months (null if unknown),
        "rationale": "one-line evidence quote"
      }}
    }}
  ]
}}

Rules:
- Only tickers explicitly named in the filing — no inference.
- Skip if counterparty is private, foreign-private, or unidentifiable.
- Multiple pairs per filing allowed. If none, return `"relations": []`.
- Output must be a single JSON object exactly matching the schema above."""


# v3 — News competitive / inverse signal (zero-sum patterns).
NEWS_COMPETITOR_PROMPT = """이 뉴스 기사는 종목 {focal_ticker}({focal_name})의 검색 결과로 수집됐다.
기사에서 {focal_ticker} 가 다른 상장사와 맺고 있는 관계가 *명시적으로* 언급된 경우에만 추출하라.
기사가 {focal_ticker}({focal_name}) 를 언급하지 않거나, 시장 일반 시황(코스피 등락 등)만 다루면 `relations: []` 를 반환하라.
시장 추측이나 같은 섹터라는 이유만으로 가짜 관계를 만들어내지 마라.

기사:
{body}

응답 JSON 객체 1개. `relations` 키 안에 배열을 넣어라:
{{
  "relations": [
    {{
      "from_ticker": "주체 종목 (KR 6자리 또는 US ticker)",
      "to_ticker": "상대 종목",
      "relation_type": "supply_upstream|supply_downstream|contract_supplier|contract_customer|competitor|complementary|peer|theme",
      "signal_direction": "positive|negative|inverse",
      "strength": 0.0~1.0,
      "confidence": 0.0~1.0,
      "metadata": {{
        "rationale": "한 줄 근거 (기사에 명시된 표현 인용)"
      }}
    }}
  ]
}}

relation_type 가이드:
- supply_upstream / contract_supplier : from_ticker 가 to_ticker 에 부품/장비/서비스를 공급
- supply_downstream / contract_customer : from_ticker 가 to_ticker 의 제품을 구매하는 고객
- competitor : 같은 시장에서 직접 경쟁 (signal_direction=inverse 권장)
- complementary : 한 쪽의 흥행이 다른 쪽도 끌어올림
- peer : 동종업계지만 직접 경쟁/공급 관계 아님
- theme : 같은 매크로/정책 테마 (반도체 사이클, AI 데이터센터 등)

규칙:
- 양쪽 ticker 모두 한국 6자리(005930) 또는 US 1-5자(AAPL) 형식으로만 표기
- {focal_ticker}({focal_name}) 가 기사 본문/제목에 *실제로* 등장한 관계만 추출. focal 이 양쪽 어디에도 포함되지 않는 관계는 응답에서 제외
- 시장 추측이 아닌 기사에 명시된 관계만
- 추출할 게 없으면 `{{"relations": []}}`"""


# Generic schema reminder appended at the end of every prompt for retry-on-fail.
SCHEMA_REMINDER = """\
\n\nIMPORTANT: respond with a JSON array. Each element must have exactly these keys: \
from_ticker, to_ticker, relation_type, signal_direction, strength, confidence, \
valid_from, valid_until, metadata. No prose, no code fences, no explanation."""
