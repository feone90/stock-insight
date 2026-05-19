"""Stage 2 synthesizer — judgment-only LLM call.

Produces `AnalystOutput` (4 LLM fields: glance, thesis, relations_narrative,
decision + interp_citations). Data fields (technical, macro, fundamentals,
news, relations_data) come from `data_layer.assemble_data_layer` and are
merged with this output by `engine.compose`.

Retries once on validation failure with a stricter prompt; second failure
raises ValueError so the engine can fall back to stale data.

Persona is `analyst_v1` (see persona.py) — internal naming only, never
surfaced to the UI.
"""
from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from app.schemas.card import AnalystOutput
from app.services.analyst import get_analyst_adapter
from app.services.analyst.persona import ANALYST_V1

logger = logging.getLogger(__name__)

RESEARCH_BLOB_MAX = 14000  # leave headroom under total prompt limit
PROMPT_SIZE_SOFT_LIMIT = 19000  # bumped from 18K to fit family-friendly copy guidelines

_FIELD_INSTRUCTIONS = """\
출력 JSON에 다음 4개 분석 필드만 포함하라. 데이터 echoing 금지.

문장 스타일 강제:
- 내부 분석은 전문가 수준으로 하되, 출력 문장은 가족 비전공자용 투자 메모다.
- 결론을 먼저 쓴다. "왜냐하면" 뒤에 핵심 근거 1~2개만 붙인다.
- 전문용어를 그대로 쓰지 마라. 쓰면 쉬운 말로 풀어 쓴다.
- 각 문자열은 짧게. 한 문장에 한 가지 의미. 긴 보고서 문체 금지.
- enum 값(BULL/BASE/BEAR, BUY/WATCH/REJECT)은 schema 때문에 유지하지만, 자연어 문장에는 "좋은 경우/기본 경우/나쁜 경우", "매수 후보/관망/보류"처럼 풀어 쓴다.

1) glance
   { final_grade: "S"|"A"|"B"|"C"|"D",
     grade_delta: "up"|"down"|"same"|null,
     stance: "BUY"|"WATCH"|"REJECT",
     entry_stage: "ENTER"|"WAIT"|"REJECT",
     one_line: str,
     citations: list[int] }   # interp_citations 풀에서 참조
   - one_line: 60~90자. "지금 행동 판단 + 가장 큰 이유" 순서.
     예: "지금은 추격매수보다 대기. 가격은 올랐지만 거래량과 새 호재가 약하다."

2) thesis
   { core_thesis: str,
     supports: list[Claim] (≥3),
     opposes: list[Claim] (≥2),
     catalysts: list[Catalyst],            # 14일 윈도 내 없으면 빈 배열
     no_catalysts_reason: str|null,         # catalysts=[] 일 때 반드시 채우기
     scenarios: list[Scenario] (정확히 3개: BULL/BASE/BEAR, 확률 합 ≈ 1.0),
     citations: list[int] }

   Claim = { text: str, citations: list[int], interpretation: {kind, based_on, rationale}|null }
   Catalyst = { when, event, impact_estimate, direction: "positive"|"negative"|"mixed", citation_ids: list[int] }
   Scenario = { name: "BULL"|"BASE"|"BEAR", probability: 0..1, scenario_price: float|null,
                scenario_change_pct: float|null, rationale: str }
   - core_thesis: 최대 2문장. "이 종목을 좋게/나쁘게 보는 핵심 이유"만.
   - supports/opposes[].text: 각 1문장. "사실 + 투자 판단상 의미"를 함께 쓴다.
     나쁜 예: "컨센서스 상회 가능성." 좋은 예: "시장 기대보다 실적이 잘 나오면 비싼 주가 부담을 일부 덜 수 있다."
   - Scenario.rationale: 쉬운 말로. "좋은 경우/기본 경우/나쁜 경우"에 해당하는 조건과 결과를 쓴다.
   - Catalyst.event/impact_estimate: 일정 이름보다 "주가에 왜 중요한지"가 보이게 쓴다.

3) relations_narrative
   { one_line: str,                          # 종목과 peer/공급망/그룹/테마/매크로 관계 한 줄 요약
     notes_by_target: { ticker_or_theme: str },  # 각 관계 target에 대한 짧은 해설 (선택)
     citations: list[int] }
   - one_line: 관계를 나열하지 말고 "매매 판단에 왜 중요한지"를 한 줄로 쓴다.
   - notes_by_target 값: 1문장. 공급망/경쟁/고객 관계가 주가에 미치는 방향을 쉬운 말로.

4) decision
   { stance, sizing_note, support_price, risk_threshold, citations,
     interpretation: {kind, based_on, rationale}|null }
   note 필드는 출력하지 마라 — 서버가 주입한다.
   - sizing_note: 반드시 행동으로 시작. 예: "지금은 소액만", "지금은 기다림", "손절 기준 없으면 매수 보류".
   - support_price/risk_threshold가 있으면 sizing_note에서 그 가격이 어떤 의미인지 쉬운 말로 설명.

추가:
- interp_citations: list[Citation]
  Citation = { id: int, source_type: "db"|"market_data"|"news"|"disclosure"|"web"|"curated_relation",
               label: str, url: str|null, timestamp: str|null }
  · timestamp는 ISO 8601 단일 시점(YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM:SS)만 허용. 범위(YYYY-MM-DD~YYYY-MM-DD), 라벨, 설명문 절대 금지. 모르면 null.
  · 해석 풀의 citation은 *드물게* 등장 — 리서처가 가져온 데이터 외에 네가 *새로* 도입한 출처에 한해 등록. 등록할 게 없으면 빈 배열 [].
  · 데이터 layer가 이미 채워줄 영역(지표/매크로/재무/뉴스/관계 구조)은 너의 citation으로 등록하지 마라.
  · id는 1부터 순차. 위 4개 필드의 citations: list[int] 는 이 풀의 id를 참조한다.

엄수:
- 출력은 ticker/name/market/price/sector 등 메타데이터 포함 X (서버 주입).
- technical/macro/fundamentals/news/relations 데이터 필드 포함 X (data_layer 책임).
- catalysts 빈 배열이면 no_catalysts_reason 필수.
- scenarios는 정확히 BULL/BASE/BEAR 3개. 확률 합 0.95~1.05.
- supports ≥ 3, opposes ≥ 2 (편향 방지).
- 모든 citations / citation_ids / based_on 의 list[int] 는 위 interp_citations에 *직접 등록한* id (1..M)만 참조. 등록 안 한 id 절대 사용 금지. 참조할 게 없으면 빈 배열 [].
- JSON 객체 1개만 출력. 코드 펜스 / 마크다운 금지.
"""


def _build_prompt(ticker: str, research: dict, retry: bool = False) -> str:
    research_blob = json.dumps(research, ensure_ascii=False, default=str)[:RESEARCH_BLOB_MAX]
    parts = [
        ANALYST_V1,
        "\n\n---\n\n",
        f"종목 ticker = {ticker}\n\n",
        f"리서처가 모은 증거 (JSON):\n{research_blob}\n\n",
        _FIELD_INSTRUCTIONS,
    ]
    if retry:
        parts.append(
            "\n[재시도] 이전 응답이 스키마 검증 실패. "
            "필수 필드 모두 채우고 enum 정확히. "
            "supports ≥3, opposes ≥2, scenarios 정확히 BULL/BASE/BEAR 3개. "
            "interp_citations[].timestamp는 ISO 8601 단일 날짜(YYYY-MM-DD)만, "
            "범위/라벨/설명문 금지, 모르면 null. "
            "모든 citations/citation_ids/based_on은 interp_citations에 등록한 id만 참조 "
            "(등록 안 한 id 사용 금지). "
            "JSON 1개만, 코드 펜스 X."
        )
    return "".join(parts)


async def run_synthesize(
    ticker: str, research: dict, max_retries: int = 1
) -> AnalystOutput:
    """LLM → AnalystOutput. Retries on validation error up to `max_retries`.

    Stage-2 produces ONLY analyst judgment. Data sections (technical/macro/
    fundamentals/news/relations_data) come from `data_layer.assemble_data_layer`
    and are merged at `engine.compose` — not here.
    """
    adapter = get_analyst_adapter()

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        prompt = _build_prompt(ticker, research, retry=attempt > 0)
        prompt_size = len(prompt.encode("utf-8"))
        logger.info(
            "synthesize[%s] attempt %d prompt size=%d bytes",
            ticker, attempt + 1, prompt_size,
        )
        if prompt_size > PROMPT_SIZE_SOFT_LIMIT:
            logger.warning(
                "synthesize[%s] prompt size %d exceeds soft limit %d",
                ticker, prompt_size, PROMPT_SIZE_SOFT_LIMIT,
            )

        try:
            raw_text = await adapter.generate_json(prompt)
        except Exception as e:
            last_error = e
            logger.warning(
                "synthesize[%s] attempt %d adapter error: %s",
                ticker, attempt + 1, e,
            )
            continue

        try:
            raw = json.loads(raw_text) if isinstance(raw_text, str) else raw_text
        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(
                "synthesize[%s] attempt %d JSON parse error: %s; raw[:500]=%r",
                ticker, attempt + 1, e, (raw_text or "")[:500],
            )
            continue

        if isinstance(raw, dict):
            logger.info(
                "synthesize[%s] attempt %d received keys=%s",
                ticker, attempt + 1, sorted(raw.keys()),
            )

        try:
            return AnalystOutput.model_validate(raw)
        except ValidationError as e:
            last_error = e
            logger.warning(
                "synthesize[%s] attempt %d validation error: %s",
                ticker, attempt + 1, e,
            )
            continue

    raise ValueError(
        f"synthesize failed after {max_retries + 1} attempts: {last_error}"
    )
