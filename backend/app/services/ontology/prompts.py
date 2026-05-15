"""LLM extraction prompts — DART / SEC / news / web.

Each prompt is a Python format string. `{body}` placeholder is the raw text;
extractor concatenates the schema reminder before sending. Output is a bare
JSON array; `ExtractionBatch.relations` parses both array and `{relations:...}`.

Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §6
Plan: docs/superpowers/plans/2026-04-30-p1.6-relation-extraction.md §6.2~6.4
"""

# v1 — KR DART contract disclosures (단일판매·공급계약 / 주요공급계약).
# 2026-05-15 시니어 redesign — news prompt 와 동일 패턴 (filing subject =
# 발행자 고정, audit 가능 SVO 인용 + few-shot REJECT/KEEP).
DART_CONTRACT_PROMPT = """역할: 너는 한국 DART 공시를 audit 하는 시니어 셀사이드 애널리스트다. 두 상장사 사이의 *명시적*이고 *검증 가능한* 공급/구매 계약만 추출한다. 추정·언론보도 인용·검토 단계 X.

가장 중요한 원칙:
- DART 공시는 *발행자* 가 자기 사업 사실을 보고하는 자료다. 발행자 = subject. 상대방 ticker 만 다양.
- 단순 "협력 검토", "MOU 체결 가능성", "수주 추진 중" 같은 *확정 안 된* 표현은 계약이 아니다. 본 계약 체결만 추출.
- 상대방이 비상장이면 추출 X (universe match 안 됨). 비상장 entity 는 RelationCandidate 가 별도 처리.

공시 본문:
{body}

반드시 먼저 수행할 FILING SUBJECT IDENTIFICATION:
Step 1: 본 공시의 발행자(filer)는 어떤 회사/종목코드인가?
- 공시 본문 상단 또는 보고자 항목에 명시. 정확한 6자리 종목코드까지.

Step 2: 본 공시가 *체결 완료된* 공급/구매 계약을 다루는가? (yes/no)
- yes 신호: "계약 체결", "공급 계약 보고", "단일판매·공급계약", "수주 통보", "공시 일자 N월 N일 계약 체결"
- no 신호: "협력 검토", "MOU 체결 가능성", "잠재 수주", "협상 진행 중", "추진 예정", "기대"
- 인사 변경 / 자회사 설립 / 자금 조달 공시는 X — 계약 본문 아님.

Step 3:
- Step 2 가 no 이면 즉시 `relations: []` 반환하고 종료.
- yes 이면 상대방 (counterparty) 식별 단계로 진행.

Step 4 (yes 경우만): 계약 상대방이 상장사인가?
- 상장사 = KR 6자리 또는 US 1-5자 ticker 확인 가능.
- 비상장 / 외국계 / 컨소시엄 / 정부기관 → 그 relation 추출 X.

추출 대상 — `contract_supplier` 또는 `contract_customer`:
- 발행자가 공급자(셀러)면 → from_ticker=발행자, to_ticker=상대방, relation_type=contract_supplier
- 발행자가 구매자(바이어)면 → from_ticker=발행자, to_ticker=상대방, relation_type=contract_customer

SVO QUOTE 필수 (metadata.svo_quote):
각 relation 의 metadata.svo_quote 에는 *공시 본문에서 그대로 인용한* 계약 문장 하나를 박아라.
- 발행자가 주어/목적어 + 계약 동사 + 상대방 명시.
- 예시 OK: "당사는 ㈜A 와 1,200억원 규모의 EUV 마스크 공급 계약을 체결하였습니다."
- 예시 X: "협력 관계 강화 검토 중", "MOU 체결 가능성 있음" — 동사가 추정/검토.
- svo_quote 가 없으면 그 relation 추출 X.

confidence 기준 (엄격):
- 0.85 이상: 계약 금액(KRW) + 일자 + 상대방 ticker 모두 명시
- 0.7~0.85: 금액 또는 일자 일부 누락, 그래도 계약 체결 사실 명확
- 0.5~0.7: 정성적 계약 사실만 (가급적 0.7 이상에서만 추출)
- < 0.5: 절대 추출 X

few-shot examples:

KEEP 1 — 명시적 공급 계약:
본문 인용: "당사는 SK하이닉스(000660)와 1,200억원 규모의 HBM 검사장비 공급 계약을 2026-05-10 일자로 체결하였습니다."
출력: {{"thinking":"Step 1: 발행자=048300. Step 2: yes — 명시적 계약 체결 + 금액 + 일자. Step 3: 진행. Step 4: 상대방 000660 상장사.","relations":[{{"from_ticker":"048300","to_ticker":"000660","relation_type":"contract_supplier","signal_direction":"positive","strength":0.85,"confidence":0.9,"valid_from":"2026-05-10","valid_until":null,"metadata":{{"value_krw":120000000000,"term_months":null,"rationale":"SK하이닉스에 HBM 검사장비 1,200억원 공급 계약 체결","svo_quote":"당사는 SK하이닉스(000660)와 1,200억원 규모의 HBM 검사장비 공급 계약을 2026-05-10 일자로 체결하였습니다."}}}}]}}

REJECT 1 — 협력 검토 단계:
본문 인용: "당사는 삼성전자와 차세대 메모리 공동 개발 협력을 검토하고 있습니다."
판정: Step 2 = no ("검토 중" 은 계약 체결 X).
출력: {{"thinking":"Step 1: 발행자=XXXXXX. Step 2: no — '검토하고 있습니다' 는 확정 계약이 아닌 추진 단계. Step 3: 종료.","relations":[]}}

REJECT 2 — 비상장 상대방:
본문 인용: "당사는 ㈜비상장코퍼레이션과 N억 규모 부품 공급 계약을 체결하였습니다."
판정: Step 4 = no (상장 ticker 없음).
출력: {{"thinking":"Step 1: 발행자=XXXXXX. Step 2: yes — 계약 체결. Step 3: 진행. Step 4: 상대방 비상장 — 추출 X.","relations":[]}}

REJECT 3 — 자기 내부 거래:
본문 인용: "당사 자회사 ㈜A 가 모회사인 본사와 사내 거래를 진행하였습니다."
판정: 자기 그룹 내 거래는 외부 관계 아님.
출력: {{"thinking":"Step 1: 발행자=XXXXXX. Step 2: yes 처럼 보이나 자회사-모회사 내부 거래. Step 3: 외부 사업 관계 아님 — 추출 X.","relations":[]}}

최종 응답 JSON schema (자연어 / 코드펜스 X):
{{
  "thinking": "Step 1: 발행자=...  Step 2: yes/no + 한 줄 근거. Step 3: 진행 또는 종료. Step 4 (yes 경우): 상장/비상장.",
  "relations": [
    {{
      "from_ticker": "발행자 종목코드 (KR 6자리 또는 US ticker)",
      "to_ticker": "상대방 종목코드",
      "relation_type": "contract_supplier | contract_customer",
      "signal_direction": "positive",
      "strength": 0.0~1.0,
      "confidence": 0.0~1.0,
      "valid_from": "YYYY-MM-DD" 또는 null,
      "valid_until": "YYYY-MM-DD" 또는 null,
      "metadata": {{
        "value_krw": 계약금액 KRW (숫자, 모르면 null),
        "term_months": 계약 기간 개월수 (모르면 null),
        "rationale": "근거 한 줄 (svo_quote 요약 가능)",
        "svo_quote": "공시 본문에서 그대로 인용한 계약 문장 하나"
      }}
    }}
  ]
}}

출력 규칙:
- JSON 객체 1개만. 설명 문장 X.
- Step 2 가 no 이면 relations 는 반드시 [].
- svo_quote 없으면 해당 relation 추출 X.
- rationale 에 "검토 중 / 추진 / 가능성 / 기대 / 추정" 들어가면 그 relation 자체 X."""


# v2 — US SEC 8-K Item 1.01 (Material Definitive Agreement) contract.
# 2026-05-15 senior redesign — same pattern as DART_CONTRACT_PROMPT (filing
# subject = filer fixed, audit-grade SVO quote + few-shot REJECT/KEEP).
SEC_8K_CONTRACT_PROMPT = """Role: You are a senior sell-side analyst auditing US SEC 8-K filings. Extract only *explicit and verifiable* contractual relationships between two publicly listed companies. No inference, no press-release language, no exploratory talks.

Most important principles:
- An 8-K filing reports the *filer*'s own business facts. Filer = subject. Only the counterparty varies.
- "Letter of intent", "MOU", "discussions", "exploring", "may enter into" — these are NOT executed contracts. Only signed/effective agreements count.
- If the counterparty is private or unidentifiable, do not extract (universe match will fail). Private entities are buffered separately.

Filing body:
{body}

FILING SUBJECT IDENTIFICATION (mandatory first):
Step 1: Who is the filer of this 8-K? (US 1-5 letter ticker, found in filing header)

Step 2: Does the filing report an *executed* material definitive agreement (Item 1.01) or contract? (yes/no)
- yes signals: "entered into", "executed", "signed", "the parties have agreed", "effective as of [date]"
- no signals: "intends to", "expects to", "is in discussions", "letter of intent", "MOU", "non-binding", "subject to"
- Non-contract items (officer departures, financing, restructuring) → no.

Step 3:
- If Step 2 is no → return `relations: []` immediately and stop.
- If yes → proceed to counterparty identification.

Step 4 (yes path): Is the counterparty a publicly listed company?
- Listed = US 1-5 letter ticker or KR 6-digit code resolvable.
- Private / sovereign / consortium / subsidiary-only → drop that relation.

Extraction targets — `contract_supplier` or `contract_customer`:
- If filer is supplier/seller → from_ticker=filer, to_ticker=counterparty, relation_type=contract_supplier
- If filer is customer/buyer → from_ticker=filer, to_ticker=counterparty, relation_type=contract_customer

SVO QUOTE REQUIRED (metadata.svo_quote):
Each relation's `metadata.svo_quote` must contain *one verbatim sentence* from the filing body.
- Filer appears as subject or object + contract verb + counterparty name.
- OK: "On May 10, 2026, the Company entered into a Supply Agreement with Nvidia Corporation under which the Company will provide HBM3E memory modules."
- NOT OK: "The Company is exploring a potential partnership", "The Company may enter into an agreement" — verb is exploratory.
- If no qualifying svo_quote, drop the relation.

confidence thresholds (strict):
- ≥ 0.85: Contract value (USD) + effective date + counterparty ticker all named.
- 0.7–0.85: Value or date missing, but execution clear.
- 0.5–0.7: Qualitative only (prefer 0.7+ thresholds for extraction).
- < 0.5: Never extract.

few-shot examples:

KEEP 1 — Explicit supply contract:
Filing quote: "On May 10, 2026, the Company entered into a Manufacturing Services Agreement with NVIDIA Corporation (Nasdaq: NVDA) pursuant to which the Company will supply HBM3E memory modules valued at approximately $850 million through December 2027."
Output: {{"thinking":"Step 1: filer=MU. Step 2: yes — 'entered into ... Manufacturing Services Agreement' + date + value. Step 3: proceed. Step 4: counterparty NVDA is public.","relations":[{{"from_ticker":"MU","to_ticker":"NVDA","relation_type":"contract_supplier","signal_direction":"positive","strength":0.85,"confidence":0.9,"valid_from":"2026-05-10","valid_until":"2027-12-31","metadata":{{"value_usd":850000000,"term_months":19,"rationale":"Supplies HBM3E to NVIDIA, $850M through Dec 2027","svo_quote":"On May 10, 2026, the Company entered into a Manufacturing Services Agreement with NVIDIA Corporation (Nasdaq: NVDA) pursuant to which the Company will supply HBM3E memory modules valued at approximately $850 million through December 2027."}}}}]}}

REJECT 1 — Letter of intent (no execution):
Filing quote: "The Company executed a non-binding letter of intent with Acme Corp. regarding potential collaboration on next-generation products."
Verdict: Step 2 = no ("non-binding letter of intent" + "potential" = not executed contract).
Output: {{"thinking":"Step 1: filer=XXX. Step 2: no — non-binding LOI is not an executed agreement. Step 3: stop.","relations":[]}}

REJECT 2 — Private counterparty:
Filing quote: "The Company entered into a supply agreement with PrivateCo LLC, a privately-held semiconductor packaging firm."
Verdict: Step 4 = no (counterparty private, no ticker resolvable).
Output: {{"thinking":"Step 1: filer=XXX. Step 2: yes — entered into agreement. Step 3: proceed. Step 4: counterparty is private — drop relation.","relations":[]}}

REJECT 3 — Internal restructuring / non-contract item:
Filing quote: "The Board of Directors of the Company appointed Jane Doe as Chief Financial Officer effective June 1, 2026."
Verdict: Step 2 = no (officer appointment, not contract).
Output: {{"thinking":"Step 1: filer=XXX. Step 2: no — officer appointment is not a material definitive agreement. Step 3: stop.","relations":[]}}

Final JSON schema (no prose, no code fences):
{{
  "thinking": "Step 1: filer=... Step 2: yes/no + one-line reason. Step 3: proceed or stop. Step 4 (if yes): public/private.",
  "relations": [
    {{
      "from_ticker": "filer ticker (US 1-5 letters or KR 6-digit)",
      "to_ticker": "counterparty ticker",
      "relation_type": "contract_supplier | contract_customer",
      "signal_direction": "positive",
      "strength": 0.0~1.0,
      "confidence": 0.0~1.0,
      "valid_from": "YYYY-MM-DD" or null,
      "valid_until": "YYYY-MM-DD" or null,
      "metadata": {{
        "value_usd": numeric USD amount (null if not stated),
        "term_months": contract term months (null if unknown),
        "rationale": "one-line summary of the relation",
        "svo_quote": "one verbatim sentence from the filing body"
      }}
    }}
  ]
}}

Output rules:
- Single JSON object only. No prose.
- If Step 2 is no, relations MUST be [].
- If svo_quote missing, drop that relation.
- If rationale would contain "may", "could", "potentially", "is exploring", "non-binding", "letter of intent", drop the relation."""


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
# 2026-05-15 시니어 redesign — SVO quote 필수 + few-shot REJECT/KEEP + hedge
# hard reject. news/DART/SEC 8-K 와 동일 패턴.
TEN_K_RISK_PROMPT = """역할: 너는 시니어 셀사이드 애널리스트다. 미국 SEC 10-K 의 Item 1A. Risk Factors 를 읽고, 본 회사({focal_ticker}/{focal_name})와 *사업 본질로 얽힌 다른 상장 회사* 만 추출한다.

가장 중요한 원칙:
- 10-K Risk Factors 는 *발행자가 SEC 에 자기 risk 를 보고* 하는 자료다. 발행자 = `{focal_ticker}` 고정 subject.
- 일반론적 risk ("we face competition") 는 추출 대상 X. 회사 이름 또는 ticker 가 *명시*된 risk 만.
- 발행자 자신과의 관계 추출 금지 — to_ticker = {focal_ticker} 면 drop.

10-K Item 1A. Risk Factors:
{body}

FILING SUBJECT 확인 (mandatory):
Step 1: 발행자 = {focal_ticker}({focal_name}) — 본 10-K 의 reporter.
Step 2: 추출 대상 risk 문장이 *구체 회사명* 또는 *ticker* 를 명시하는가?
- yes 신호: "Our largest customers include Apple Inc. and Microsoft Corporation", "We rely on TSMC (TWSE: 2330)", "We compete with NVIDIA Corporation"
- no 신호: "We face competition from various companies", "Our suppliers are subject to risks" (회사명 X)
Step 3: no 이면 그 문장은 추출 X. yes 인 문장만 SVO 단계로.

추출 대상 — 다음 카테고리만:
- contract_customer  : "Our largest customers include X" / "Revenue from X represented N% of total revenue"
- contract_supplier  : "We rely on X for [EUV / HBM / GPU / etc.]" / "X is a sole supplier"
- competitor         : "We compete with X" / "X is our primary competitor in [market]"
- regulatory_link    : "Like X, we are subject to [export controls / FDA / antitrust]" 같은 동일 규제 노출

SVO QUOTE 필수 (metadata.svo_quote):
각 relation 은 본문에서 *그대로 인용한* SVO 문장 하나를 반드시 가져야 함.
- 발행자 또는 to_ticker 가 주어/목적어 + 사업 동사 + 상대방 명시.
- 동사 예시: rely on, supply, compete with, derive revenue from, license from, source from
- svo_quote 없으면 그 relation 추출 X.

HEDGE / GENERIC 즉시 거절:
- "could be affected by", "may face", "uncertain", "is subject to" + 회사명 미명시 → drop
- "such as X" 식 *예시 enumeration* + 본 회사와 *명시적* 사업 관계 X → drop
- "various", "some", "certain", "a few" 같은 막연 수식 → drop

confidence 기준:
- 0.85+ : ticker 또는 회사 풀네임 직접 명시 + 매출 비중/지위 등 구체 인용
- 0.6~0.85 : 회사명 명시 + 정성적 인용
- < 0.6 : 절대 추출 X

few-shot examples:

KEEP 1 — Customer concentration with %:
본문: "In fiscal 2025, Apple Inc. accounted for approximately 26% of our net sales, and our top three customers including Apple, Sony Group, and HP Inc. represented 47% of net sales."
출력 relation: {{"from_ticker":"AVGO","to_ticker":"AAPL","relation_type":"contract_customer","signal_direction":"negative","strength":0.85,"confidence":0.9,"metadata":{{"rationale":"Apple은 매출의 26% — 단일 최대 고객","svo_quote":"In fiscal 2025, Apple Inc. accounted for approximately 26% of our net sales","customer_concentration_pct":26,"concentration_phrase":"Apple Inc. accounted for approximately 26% of our net sales","top_customer_names":["AAPL","SONY","HPQ"]}}}}

KEEP 2 — Sole supplier:
본문: "We rely on Taiwan Semiconductor Manufacturing Company (TWSE: 2330) as the sole foundry for our advanced node products."
출력 relation: {{"from_ticker":"NVDA","to_ticker":"TSM","relation_type":"contract_supplier","signal_direction":"negative","strength":0.85,"confidence":0.88,"metadata":{{"rationale":"TSMC는 advanced node 의 sole foundry — 단일 공급 의존","svo_quote":"We rely on Taiwan Semiconductor Manufacturing Company (TWSE: 2330) as the sole foundry for our advanced node products."}}}}

REJECT 1 — Abstract competition risk:
본문: "We operate in a highly competitive industry and face competition from various companies, some of which may have greater resources."
판정: 회사 이름 *명시 X* — Step 2=no.
출력: {{"thinking":"Step 1: filer={focal_ticker}. Step 2: no — '다양한 회사 (various companies)' 만 언급, 구체 회사명 없음. Step 3: 추출 X.","relations":[]}}

REJECT 2 — Such as enumeration without business relation:
본문: "Many of our peers in the technology sector, such as Apple, Microsoft, and Google, have faced similar regulatory scrutiny."
판정: 회사명 enumerate 됐지만 *peer* 비교일 뿐 발행자와의 specific 사업 관계 X.
출력: {{"thinking":"Step 1: filer={focal_ticker}. Step 2: yes 회사명 명시, 그러나 'peer ... faced similar scrutiny' 는 발행자-target 사업 관계 SVO 가 아닌 단순 enumeration. 추출 X.","relations":[]}}

REJECT 3 — Self-mention:
본문: "If we fail to compete effectively, our results may decline."
판정: focal 자신만 등장.
출력: {{"thinking":"Step 1: filer={focal_ticker}. Step 2: no — 발행자 자신만 언급, 다른 회사 X. 추출 X.","relations":[]}}

최종 응답 JSON schema (자연어 / 코드펜스 X):
{{
  "thinking": "Step 1: filer={focal_ticker}. Step 2: yes/no + 한 줄 근거. Step 3: 진행 또는 종료.",
  "relations": [
    {{
      "from_ticker": "{focal_ticker}",
      "to_ticker": "상대 회사 ticker (US 1-5자) 또는 KR 6자리",
      "relation_type": "contract_customer | contract_supplier | competitor | regulatory_link",
      "signal_direction": "positive | negative | inverse",
      "strength": 0.0~1.0,
      "confidence": 0.0~1.0,
      "metadata": {{
        "rationale": "Risk Factors 인용 한 줄 요약",
        "svo_quote": "본문에서 *그대로 인용한* SVO 문장 하나",
        "customer_concentration_pct": "contract_customer 일 때만, 본문에 % 명시되면 숫자 (생략 가능)",
        "concentration_phrase": "본문 *그대로 인용*된 % 문장 (% 명시될 때만)",
        "top_customer_names": "list of tickers (선택)"
      }}
    }}
  ]
}}

출력 규칙:
- from_ticker 는 반드시 `{focal_ticker}`. to_ticker 만 다양.
- to_ticker 가 `{focal_ticker}` 와 같으면 drop (self-reference).
- ticker 미명시 회사명 OK 하되 가장 잘 알려진 ticker 사용 ("ASML Holding"→"ASML", "Taiwan Semiconductor"→"TSM"). 모호하면 drop.
- svo_quote 없으면 그 relation 추출 X.
- 회사 이름이 본문 *어디에도 명시되지 않으면* `"relations": []`.

### Customer concentration 보강 (Codex review I)
contract_customer 추출 시 본문에 *정량적 매출 의존* 표현 ("X accounted for 25% of revenue" 등) 있으면 metadata.customer_concentration_pct (숫자) + concentration_phrase (그대로 인용) 박아라. 추정/계산 금지 — 본문에 % 가 명시 안 됐으면 두 키 모두 생략."""


# Generic schema reminder appended at the end of every prompt for retry-on-fail.
SCHEMA_REMINDER = """\
\n\nIMPORTANT: respond with a JSON array. Each element must have exactly these keys: \
from_ticker, to_ticker, relation_type, signal_direction, strength, confidence, \
valid_from, valid_until, metadata. No prose, no code fences, no explanation."""
