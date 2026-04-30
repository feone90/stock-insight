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
NEWS_COMPETITOR_PROMPT = """다음 뉴스 기사에서 두 상장사 사이의 경쟁/대립 관계를 추출하라.
A의 부정적 이슈가 B에게 호재로 작용하는 패턴을 우선 포착하라.

기사:
{body}

응답 JSON 객체 1개. `relations` 키 안에 배열을 넣어라:
{{
  "relations": [
    {{
      "from_ticker": "이슈 발생 종목",
      "to_ticker": "영향받는 종목",
      "relation_type": "competitor",
      "signal_direction": "inverse",
      "strength": 0.0~1.0,
      "confidence": 0.0~1.0,
      "metadata": {{
        "rationale": "한 줄 근거"
      }}
    }}
  ]
}}

규칙:
- competitor 외 contract / complementary 발견 시 함께 응답
- 시장 추측이 아닌 기사에 명시된 관계만
- 양쪽 ticker 모두 명시되어야 응답. 없으면 `relations: []`"""


# Generic schema reminder appended at the end of every prompt for retry-on-fail.
SCHEMA_REMINDER = """\
\n\nIMPORTANT: respond with a JSON array. Each element must have exactly these keys: \
from_ticker, to_ticker, relation_type, signal_direction, strength, confidence, \
valid_from, valid_until, metadata. No prose, no code fences, no explanation."""
