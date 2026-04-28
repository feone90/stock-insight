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
from sqlalchemy import select

from app.database import async_session
from app.models import Stock
from app.schemas.card import StockCard
from app.services.analyst.persona import ANALYST_V1, PERSONA_VERSION
from app.services.llm.adapter import AzureOpenAIAdapter

logger = logging.getLogger(__name__)


def _adapter():
    """Factory wrapped so tests can monkeypatch."""
    return AzureOpenAIAdapter()


async def _fetch_stock_metadata(ticker: str) -> dict:
    """DB-sourced fields the server fills. LLM never produces these."""
    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            return {"ticker": ticker}
        return {
            "ticker": stock.ticker,
            "name_ko": stock.name or "",
            "name_en": stock.name or "",
            "market": stock.market or "",
            "sector": stock.sector or "",
            "tags": [],  # frontend can derive from sector + theme relations
            "price": stock.current_price or 0.0,
            "change": stock.change or 0.0,
            "change_pct": stock.change_percent or 0.0,
            "asof": datetime.now(timezone.utc).isoformat(),
        }


def _build_prompt(ticker: str, research: dict) -> str:
    return (
        ANALYST_V1
        + "\n\n---\n\n"
        + f"종목 ticker = {ticker}\n\n"
        + f"리서처가 모은 증거 (JSON):\n{json.dumps(research, ensure_ascii=False, default=str)[:20000]}\n\n"
        + "위 증거만 사용해 다음 9개 분석 필드만 포함한 JSON을 출력하라:\n"
        + "  glance, thesis, technical, relations, news, macro, fundamentals, decision, citations\n"
        + "ticker/name/market/price/sector 등 종목 메타데이터는 서버가 주입하므로 출력 X.\n\n"
        + "필수 규칙:\n"
        + "- 각 numerical claim은 반드시 citations에 등록된 [n]을 가진다.\n"
        + "- catalysts가 14일 윈도 내에 없으면 빈 배열 + no_catalysts_reason 명시.\n"
        + "- scenarios는 BULL/BASE/BEAR 3개, 확률 합 1.0.\n"
        + "- supports ≥ 3, opposes ≥ 2.\n"
        + "- stance/entry_stage/final_grade는 enum 정확히 사용.\n"
        + "- decision 필드 반드시 포함 (stance, sizing_note, support_price, risk_threshold, citations).\n"
        + "- macro 필드 반드시 포함 (one_line, vix, fx_pairs, us_10y, sensitivities, upcoming_events, citations).\n"
        + "- citations는 top-level 배열에 각 [n] entry 등록 (id, source_type, label).\n\n"
        + "출력은 JSON 객체 1개만. 코드 펜스 금지. 마크다운 금지."
    )


async def run_synthesize(
    ticker: str, research: dict, max_retries: int = 1
) -> StockCard:
    """LLM → StockCard. Retries on validation error up to `max_retries`.

    Stock metadata (ticker, name, market, price, etc.) is server-injected
    from DB — the LLM only produces the analytical content (glance, thesis,
    technical, relations, news, macro, fundamentals, decision, citations).
    Server-controlled fields (analysis_id, generated_at, persona_version,
    schema_version) are also injected.
    """
    metadata = await _fetch_stock_metadata(ticker)
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
                "synthesize attempt %d JSON parse error: %s; raw[:500]=%r",
                attempt + 1, e, (raw_text or "")[:500]
            )
            continue
        # Diagnostic: log a fingerprint of received fields so we know if the LLM
        # is producing a full StockCard or just a stub.
        logger.info(
            "synthesize attempt %d received keys=%s (text len=%d)",
            attempt + 1, sorted(raw.keys()) if isinstance(raw, dict) else "non-dict",
            len(raw_text or ""),
        )

        # Server-inject: DB metadata wins over anything LLM tried to produce.
        raw.update(metadata)
        # Server-controlled meta
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
