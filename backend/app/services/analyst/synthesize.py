"""Stage 2: Synthesizer. Premium-tier LLM, structured StockCard output.

Consumes Stage 1 research findings + ticker, produces a Pydantic-validated
StockCard. Retries once on validation failure with a stricter prompt; second
failure raises ValueError so the engine can store stale-data fallback.

Persona is defined in `analyst_v1` (see persona.py) — internal naming only,
never surfaced to the UI.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from pydantic import ValidationError

from app.schemas.card import StockCard
from app.services.analyst.persona import ANALYST_V1, PERSONA_VERSION
from app.services.llm.adapter import AzureOpenAIAdapter

logger = logging.getLogger(__name__)


def _adapter():
    """Factory wrapped so tests can monkeypatch."""
    return AzureOpenAIAdapter()


def _build_prompt(ticker: str, research: dict) -> str:
    return (
        ANALYST_V1
        + "\n\n---\n\n"
        + f"종목 ticker = {ticker}\n\n"
        + f"리서처가 모은 증거 (JSON):\n{json.dumps(research, ensure_ascii=False, default=str)[:30000]}\n\n"
        + "위 증거만 사용해 StockCard 스키마에 정확히 맞는 JSON을 출력하라.\n"
        + "각 numerical claim은 반드시 citations에 등록된 [n]을 가진다.\n"
        + "catalysts가 14일 윈도 내에 없으면 빈 배열 + no_catalysts_reason 명시.\n"
        + "scenarios는 BULL/BASE/BEAR 3개, 확률 합 1.0.\n"
        + "supports ≥ 3, opposes ≥ 2.\n"
        + "stance/entry_stage/final_grade는 enum 정확히 사용.\n"
        + "출력은 JSON만. 코드 펜스 금지."
    )


async def run_synthesize(
    ticker: str, research: dict, max_retries: int = 1
) -> StockCard:
    """LLM → StockCard. Retries on validation error up to `max_retries`.

    Server-controlled fields (analysis_id, generated_at, persona_version,
    schema_version) are injected even if the LLM omits them.
    """
    prompt = _build_prompt(ticker, research)
    adapter = _adapter()

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        if attempt > 0:
            prompt += (
                "\n\n[재시도] 이전 응답이 스키마 검증에 실패. "
                "모든 필수 필드 채우고 enum 값 정확히 사용. JSON만 응답."
            )
        try:
            raw_text = await adapter.generate_json(prompt)
        except Exception as e:
            last_error = e
            logger.warning(
                "synthesize attempt %d adapter error: %s", attempt + 1, e
            )
            continue

        try:
            raw = json.loads(raw_text) if isinstance(raw_text, str) else raw_text
        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(
                "synthesize attempt %d JSON parse error: %s", attempt + 1, e
            )
            continue

        # Inject server-controlled fields
        raw.setdefault("analysis_id", str(uuid.uuid4()))
        raw.setdefault(
            "generated_at", datetime.now(timezone.utc).isoformat()
        )
        raw["persona_version"] = PERSONA_VERSION
        raw.setdefault("schema_version", "v1")

        try:
            return StockCard.model_validate(raw)
        except ValidationError as e:
            last_error = e
            logger.warning(
                "synthesize attempt %d validation error: %s", attempt + 1, e
            )
            continue

    raise ValueError(
        f"synthesize failed after {max_retries + 1} attempts: {last_error}"
    )
