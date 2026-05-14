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
# 2026-05-15 Codex 시니어 redesign — 사용자 발견 (Beyond Meat 기사로 NVDA↔
# McDonald's 환상 추출) 사후. 옛 prompt 는 "금지 list" 구조라 LLM 이 일단
# 뽑고 자기 모순 rationale 박는 역설. 새 prompt 는 추출 *전* article subject
# identification 게이트 + SVO 인용 강제 + few-shot REJECT/KEEP 예시 + hedge/
# self-negation hard reject.
NEWS_COMPETITOR_PROMPT = """역할: 너는 한국/미국 시장을 커버하는 시니어 셀사이드 애널리스트다.
목표는 뉴스 기사에서 {focal_ticker}({focal_name})와 다른 상장사 사이의 명시적이고 검증 가능한 사업 관계만 추출하는 것이다.

가장 중요한 원칙:
- 기사 버킷이나 검색 결과가 잘못 붙었을 수 있다. 기사 제목/본문의 primary subject가 {focal_ticker}인지 먼저 판정하라.
- {focal_ticker}가 primary subject가 아니면 어떤 관계도 추출하지 말고 즉시 relations: []를 반환하라.
- 단순 언급, 비교, 예시, 테마/ETF/섹터 동시 언급, 주가 동반 움직임, 추정성 코멘트는 사업 관계가 아니다.
- 관계를 추출하려면 기사 본문에 {focal_ticker}가 주어 또는 목적어로 등장하는 SVO 문장이 있어야 하며, 그 문장의 동사는 구체적 사업 행위여야 한다.

기사 (제목 + 본문):
{body}

반드시 먼저 수행할 ARTICLE SUBJECT IDENTIFICATION:
Step 1: 이 기사의 primary subject(주제 종목/기업)는 무엇인가?
- 기사 제목, 리드 문장, 본문 대부분이 다루는 회사/종목을 기준으로 판단한다.
- 여러 기업이 나오더라도 기사 전체의 중심 주제가 되는 기업을 하나 이상 명시하라.

Step 2: focal_ticker({focal_ticker})가 primary subject인가?
- yes/no로 답하고, 근거를 한 문장으로만 적어라.
- {focal_ticker}가 기사에서 단 한 번 언급되거나 비교/예시/맥락 설명으로만 등장하면 반드시 no다.
- {focal_ticker}가 검색 버킷 때문에 붙었더라도 기사 제목/본문의 중심 주제가 아니면 no다.

Step 3:
- Step 2가 no이면 즉시 relations: []를 반환하고 종료하라.
- Step 2가 yes인 경우에만 아래 관계 추출 단계로 진행하라.

관계 추출 대상 relation_type:
- supply_upstream: to_ticker가 from_ticker에 부품, 장비, 원재료, 기술, 라이선스 등을 공급
- supply_downstream: from_ticker가 to_ticker에 부품, 장비, 제품, 기술 등을 공급하거나 제조
- contract_supplier: to_ticker가 from_ticker의 계약상 공급자/벤더/제조 파트너
- contract_customer: to_ticker가 from_ticker의 계약상 고객/구매자/유통 파트너
- competitor: 동일 제품, 서비스, 고객, 입찰, 가격, 시장 점유율을 두고 직접 경쟁
- complementary: 한 회사의 제품/서비스 수요 증가가 다른 회사의 제품/서비스 판매 또는 사용을 직접적으로 보완
- regulatory_link: 동일한 구체 규제, 제재, 승인, 소송, 반독점, 수출통제 등에 직접 노출

SUBJECT-VERB-OBJECT 필수 요건:
각 relation은 반드시 기사 본문에서 그대로 인용하거나 거의 그대로 인용할 수 있는 SVO 문장 하나를 가져야 한다.
- SVO 문장에는 {focal_ticker} 또는 {focal_name}이 주어 또는 목적어로 등장해야 한다.
- 동사는 구체적 사업 행위여야 한다.
- 허용되는 사업 동사 예시: 공급, 계약, 인수, 협력, 경쟁, 제조, 판매, 투자, supply, acquire, partner, compete, contract, manufacture, sell, invest, provide, buy, source, launch, target.
- 단순히 같은 문단에 두 회사가 함께 등장하는 것은 충분하지 않다.
- "A와 B가 모두 상승했다", "A like B", "A such as B", "A와 B가 같은 ETF에 포함됐다"는 SVO 사업 관계가 아니다.
- metadata.svo_quote에는 이 관계를 뒷받침하는 기사 본문의 SVO 문장을 반드시 넣어라.
- svo_quote가 없으면 해당 relation은 추출 금지다.

HEDGE / MENTION-ONLY 즉시 거절:
{focal_ticker}가 아래와 같은 비교/예시/가능성/언급 맥락으로만 등장하면 관계 증거로 사용할 수 없다.
- 영어 신호: may, could, potentially, might, likely to benefit, like, such as, compared with, similar to, alongside, in the same ETF, basket, index, theme
- 한국어 신호: 예시, 비교, 관련 가능성, 수혜 기대, 동반 상승, 같은 ETF, 같은 테마, 같은 섹터, 유사한 종목, 함께 언급
- hedge language가 best available evidence인 relation은 confidence를 반드시 0.3 미만으로 보아야 하며, 따라서 절대 추출하지 말라.

RATIONALE SELF-NEGATION HARD REJECT:
너의 rationale 또는 판단 근거 문장에 아래 표현이 포함될 것 같다면, 그 relation은 절대 추출하지 말라.
- 관계 없음
- 직접적이지 않
- 직접 관련 없
- 명시되지 않
- no direct
- not directly related
- indirectly
- 간접적
이 표현이 필요하다는 것은 증거가 불충분하다는 뜻이다. 이 경우 relation을 만들지 말고 relations: [] 또는 해당 relation 제외로 처리하라.

confidence 기준:
- 0.85 이상: 구체 수치, 일자, 금액, 계약 조건, 공시, 공식 발표 또는 직접 인용이 있는 명확한 사업 관계
- 0.6 이상 0.85 미만: 수치/일자는 없지만 기사 본문에 명확한 정성적 사실로 사업 관계가 서술됨
- 0.3 이상 0.6 미만: 추정 가능하지만 기사 본문이 단정하지 않음. 원칙적으로 추출하지 말라.
- 0.3 미만: 절대 추출 금지
- hedge language, mention-only, comparison-only, ETF/index/theme co-membership은 항상 0.3 미만으로 간주하고 추출하지 말라.

few-shot examples:

REJECT 1 — Beyond Meat 기사, focal=NVDA:
기사 요약: Beyond Meat(BYND)의 생존 가능성, 비용 절감, 매출 부진을 다루는 기사. 본문 중 한 문장에서 AI chip company NVIDIA가 고성장주 비교 사례로 한 번 언급됨. McDonald's는 BYND의 식물성 버거 테스트 고객 맥락으로 언급됨.
판정:
Step 1: primary subject는 Beyond Meat/BYND다.
Step 2: focal_ticker(NVDA)가 primary subject인가? no. NVDA는 AI chip 비교 사례로 한 번 언급될 뿐 기사 주제가 아니다.
Step 3: no이므로 즉시 종료.
출력: {{"thinking":"Step 1: primary subject는 Beyond Meat/BYND입니다. Step 2: NVDA는 primary subject가 아닙니다. NVDA는 AI chip 비교 사례로만 언급됩니다. Step 3: focal_ticker가 primary subject가 아니므로 relations를 비웁니다.","relations":[]}}

REJECT 2 — ETF co-membership mention, focal=TSLA:
기사 요약: SPY ETF 리밸런싱 기사에서 TSLA와 AAPL이 같은 ETF 구성 종목으로 함께 언급됨.
판정:
Step 1: primary subject는 SPY ETF 리밸런싱이다.
Step 2: focal_ticker(TSLA)가 primary subject인가? no. TSLA는 ETF 구성 종목 예시 중 하나다.
Step 3: no이므로 즉시 종료.
출력: {{"thinking":"Step 1: primary subject는 SPY ETF 리밸런싱입니다. Step 2: TSLA는 primary subject가 아닙니다. TSLA와 AAPL은 ETF 구성 종목으로 함께 언급될 뿐입니다. Step 3: focal_ticker가 primary subject가 아니므로 relations를 비웁니다.","relations":[]}}

REJECT 3 — Hedge language, focal=MSFT:
기사 문장: "Microsoft could potentially benefit from an expansion of its OpenAI partnership."
판정: hedge language("could potentially benefit")이며 구체 SVO 사업 행위가 없다. confidence 0.3 미만이므로 추출 금지.
출력: {{"thinking":"Step 1: primary subject는 Microsoft일 수 있습니다. Step 2: MSFT는 primary subject일 수 있습니다. Step 3: 다음 단계로 진행했지만, 증거 문장이 could potentially라는 hedge language에 해당하고 구체적 사업 동사가 없어 relations를 비웁니다.","relations":[]}}

KEEP 1 — Supply contract, focal=TSMC:
기사 문장: "Apple confirmed TSMC will manufacture all A18 chips for the next iPhone cycle."
출력 relation 예시: {{"from_ticker":"TSMC","to_ticker":"AAPL","relation_type":"supply_downstream","signal_direction":"positive","strength":0.9,"confidence":0.9,"metadata":{{"rationale":"Apple confirmed TSMC will manufacture all A18 chips for the next iPhone cycle.","svo_quote":"Apple confirmed TSMC will manufacture all A18 chips for the next iPhone cycle."}}}}

KEEP 2 — M&A, focal=MSFT:
기사 문장: "Microsoft announced the acquisition of Activision Blizzard for $68.7 billion."
출력 relation 예시: {{"from_ticker":"MSFT","to_ticker":"ATVI","relation_type":"complementary","signal_direction":"positive","strength":0.92,"confidence":0.92,"metadata":{{"rationale":"Microsoft announced the acquisition of Activision Blizzard for $68.7 billion.","svo_quote":"Microsoft announced the acquisition of Activision Blizzard for $68.7 billion."}}}}

KEEP 3 — Competition, focal=NVDA:
기사 문장: "AMD launched the MI300X accelerator directly targeting NVIDIA's H100 in the datacenter AI segment."
출력 relation 예시: {{"from_ticker":"NVDA","to_ticker":"AMD","relation_type":"competitor","signal_direction":"negative","strength":0.85,"confidence":0.85,"metadata":{{"rationale":"AMD launched the MI300X accelerator directly targeting NVIDIA's H100 in the datacenter AI segment.","svo_quote":"AMD launched the MI300X accelerator directly targeting NVIDIA's H100 in the datacenter AI segment."}}}}

최종 응답 JSON schema:
{{
  "thinking": "Step 1: ... Step 2: yes/no + 근거 한 문장. Step 3: no이면 relations: [] 반환, yes이면 SVO 기반 추출 진행.",
  "relations": [
    {{
      "from_ticker": "str",
      "to_ticker": "str",
      "relation_type": "supply_upstream | supply_downstream | contract_supplier | contract_customer | competitor | complementary | regulatory_link",
      "signal_direction": "positive | negative | neutral",
      "strength": 0.0,
      "confidence": 0.0,
      "metadata": {{
        "rationale": "기사 본문에서 직접 확인되는 근거. self-negation 표현을 포함하면 안 됨.",
        "svo_quote": "기사 본문에서 그대로 인용한 SVO 문장"
      }}
    }}
  ]
}}

출력 규칙:
- JSON 객체 1개만 출력하라. 설명 문장, markdown, code fence는 출력하지 말라.
- thinking에는 Step 1, Step 2, Step 3 판정을 간결하게 포함하라.
- Step 2가 no이면 relations는 반드시 []여야 한다.
- relations 배열의 각 항목은 metadata.rationale과 metadata.svo_quote를 반드시 포함해야 한다.
- metadata.svo_quote가 기사 본문에 없거나 {focal_ticker}/{focal_name}이 SVO의 주어 또는 목적어가 아니면 해당 relation은 추출하지 말라.
- rationale에 "관계 없음", "직접적이지 않", "직접 관련 없", "명시되지 않", "no direct", "not directly related", "indirectly", "간접적" 중 하나라도 들어갈 relation은 만들지 말라.
- 판단이 애매하면 추출하지 말라."""


# v4 — US SEC 10-K Item 1A. Risk Factors 다른 회사 언급 추출.
# Codex 시니어 트레이더 권고 G (2026-05-14): 10-K Risk Factors 가 customer/
# supplier/competitor를 직접 명시한 가장 안정적 source. 8-K 14일 윈도우 /
# news 14일 윈도우 가 못 잡는 ASML 같은 capex tie-in 도 여기엔 빠짐없이 등장.
TEN_K_RISK_PROMPT = """역할: 너는 시니어 셀사이드 애널리스트다. 미국 SEC 10-K 의 Item 1A. Risk Factors 텍스트를 읽고, 본 회사({focal_ticker}/{focal_name})와 *사업 본질로 얽힌 다른 상장 회사* 만 추출하라. 일반론적 risk(예: "we face competition", "we are subject to regulation") 는 추출 대상 아니다 — 회사 이름 또는 ticker 가 명시된 경우만.

10-K Item 1A. Risk Factors:
{body}

추출 대상 — 다음 카테고리만:
- contract_customer  : "Our largest customers include X, Y" / "Revenue from X represented N% of total revenue" 같은 명시
- contract_supplier  : "We rely on X for [EUV equipment / HBM / GPU / etc.]" / "X is a sole supplier" 같은 명시
- competitor         : "We compete with X" / "X is our primary competitor in [market]" 같은 직접 경쟁
- regulatory_link    : "Like X, we are subject to [export controls / FDA / antitrust]" 같은 동일 규제 노출

confidence 기준 (엄격):
- 0.85+ : ticker 또는 회사 풀네임 직접 명시 + 매출 비중/지위 등 구체 인용
- 0.6~0.85 : 회사명 명시 + 정성적 인용
- <0.6 : 절대 추출 X

*절대 추출 X*:
- 추상적 risk ("we face competition from various companies"). 회사 이름 미명시 = drop
- 비상장 / 자회사 / sovereign / consortium
- "such as X" 식 *예시* 만 들고 본 회사와 사업 관계 없는 언급
- 자기 회사명 등장 (focal 자신과의 관계는 의미 X)

응답 JSON 객체 1개 (자연어 설명 X, code fence X):
{{
  "relations": [
    {{
      "from_ticker": "{focal_ticker}",
      "to_ticker": "상대 회사 ticker (US 1-5자) 또는 KR 6자리",
      "relation_type": "contract_customer | contract_supplier | competitor | regulatory_link",
      "signal_direction": "positive | negative | inverse",
      "strength": 0.0~1.0,
      "confidence": 0.0~1.0,
      "metadata": {{
        "rationale": "Risk Factors 텍스트에서 *그대로 인용한* 한 줄 근거. paraphrase 금지"
      }}
    }}
  ]
}}

규칙:
- from_ticker 는 반드시 `{focal_ticker}` (본 10-K 의 발행자). to_ticker 만 다양함.
- ticker 추출 우선: 본문에 "(NASDAQ: XYZ)" 같이 ticker 명시되면 그대로. 회사명만 명시되고 ticker 미명시면 가장 잘 알려진 ticker 사용 (예: "ASML Holding" → "ASML", "Taiwan Semiconductor" → "TSM"). 모호하면 추출 X.
- rationale 은 paraphrase 금지 — 텍스트 표현 그대로 인용. 인용할 표현이 없으면 그 관계 자체 추출 X.
- 회사 이름이 본문 *어디에도 명시되지 않으면* `"relations": []`

### Customer concentration 보강 (Codex review I)
contract_customer 추출 시 본문에 *정량적 매출 의존* 표현이 있으면 metadata에 같이 박아라:
- "X accounted for 25% of [our|total] revenue" / "X represents 30% of [net sales|consolidated revenue]" / "Three customers ... represented N% of revenue" 같은 명시적 % 수치.
- 위 경우 metadata 에 다음 두 키 추가:
  - `customer_concentration_pct`: 숫자 (예: 25)
  - `concentration_phrase`: 본문 *그대로 인용한* 한 줄 (paraphrase 금지)
- 추정/계산 금지. 본문에 % 가 명시 안 됐으면 두 키 모두 생략.
- "Top N customers ... 50% of revenue" 같이 합산값만 명시되면 customer_concentration_pct = 합산값 (50). top_customer_names 도 metadata 에 list 로 박을 수 있으면 박아라."""


# Generic schema reminder appended at the end of every prompt for retry-on-fail.
SCHEMA_REMINDER = """\
\n\nIMPORTANT: respond with a JSON array. Each element must have exactly these keys: \
from_ticker, to_ticker, relation_type, signal_direction, strength, confidence, \
valid_from, valid_until, metadata. No prose, no code fences, no explanation."""
