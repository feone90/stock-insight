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
NEWS_COMPETITOR_PROMPT = """역할: 너는 한국/미국 시장을 커버하는 시니어 셀사이드 애널리스트다. 한 종목의 카드에서 "이 회사와 운영상으로 얽혀 있는 다른 종목" 만 보여줘야 한다. 단순 주가 동조, 같은 섹터, 같은 인덱스, 같은 테마 ETF 편입, 시장 분위기는 *관계가 아니다*.

이 기사는 종목 {focal_ticker}({focal_name}) 검색 결과로 수집됐다. 기사에서 {focal_ticker} 와 다른 상장사 사이의 *사업 본질 관계* 가 명시된 경우에만 추출하라.

기사:
{body}

추출 대상 — 다음 사업 본질 카테고리만:
- supply_upstream / contract_supplier   : from_ticker → to_ticker 에 부품·장비·소재·라이선스를 공급 (계약/수주/벤더 지위 명시)
- supply_downstream / contract_customer : from_ticker 가 to_ticker 제품을 구매·재판매·통합 (구체 고객/매출 비중 언급)
- competitor                             : 동일 제품·서비스·고객을 두고 직접 경쟁 (시장 점유율, 입찰 충돌, 가격 인하 압박)
- complementary                          : 한쪽 수요 증가가 다른 쪽 매출/수익 직결 (보완재, 플랫폼-앱, OEM-부품)
- regulatory_link                        : 동일 규제/제재/관세에 직접 노출 (예: 미국 반도체 수출 규제 명시 대상)

*절대 추출하지 마라*:
- "코스피/코스닥 동반 상승/하락" 같은 시장 시황
- "같은 반도체주", "같은 AI 테마", "같은 ETF 포함" 같은 카테고리 동거
- "외국인 매수세 유입" 같은 수급 동조
- "전문가들은 ... 일 수 있다" 같은 추측성 코멘트
- 기자가 시장 분석을 위해 단순 나열한 비교 종목

위 카테고리에 해당해도 *기사 본문이 사업 관계의 구체 표현* (공급, 수주, 계약, 채택, 점유율, 경쟁, 규제) 을 직접 담지 않으면 제외하라. 추측·동조·인덱스 편입 만으로는 부족하다.

응답 JSON 객체 1개:
{{
  "relations": [
    {{
      "from_ticker": "주체 종목 (KR 6자리 또는 US 1-5자)",
      "to_ticker": "상대 종목 (동일 포맷)",
      "relation_type": "supply_upstream | supply_downstream | contract_supplier | contract_customer | competitor | complementary | regulatory_link",
      "signal_direction": "positive | negative | inverse",
      "strength": 0.0~1.0,
      "confidence": 0.0~1.0,
      "metadata": {{
        "rationale": "기사 본문에서 *그대로 인용한* 한 줄 근거 (paraphrase 금지)"
      }}
    }}
  ]
}}

confidence 기준 (엄격히 적용):
- 0.85+ : 기사에 계약/수주/지분/규제 노출이 *구체 수치/일자/공시 인용* 으로 명시 (예: "1,200억원 공급 계약 체결", "지분 5% 취득", "EAR 적용 대상")
- 0.6~0.85 : 사업 관계는 명시되나 수치/일자 부재. 정성적 인용 위주
- 0.3~0.6 : 사업 관계 추정 가능하지만 기사가 단정하지 않음. 가급적 제외
- <0.3 : 절대 추출 X

규칙:
- 양쪽 ticker 모두 한국 6자리(005930) 또는 US 1-5자(AAPL) 형식만
- {focal_ticker}({focal_name}) 가 기사 본문/제목에 *실제로* 나온 관계만. focal 이 양쪽 어디에도 없으면 응답에서 제외
- rationale 은 paraphrase 금지 — 기사 표현 그대로 인용. 인용할 만한 표현이 없으면 해당 관계 자체 추출 X
- 사업 관계가 *기사 어디에도* 명시되지 않거나, 위 "절대 추출 X" 케이스만 보이면 `{{"relations": []}}`"""


# Generic schema reminder appended at the end of every prompt for retry-on-fail.
SCHEMA_REMINDER = """\
\n\nIMPORTANT: respond with a JSON array. Each element must have exactly these keys: \
from_ticker, to_ticker, relation_type, signal_direction, strength, confidence, \
valid_from, valid_until, metadata. No prose, no code fences, no explanation."""
