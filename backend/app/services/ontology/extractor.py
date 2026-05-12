"""LLM RAG extraction — source-agnostic.

Same flow for DART / SEC / news / web:
  1. Build prompt (per-source template + body)
  2. Call LLM with JSON mode
  3. Parse → Pydantic `ExtractionBatch.relations`
  4. ValidationError or JSON error → retry once with schema reminder
  5. Hard fail → return [] + log

Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §6
Plan: docs/superpowers/plans/2026-04-30-p1.6-relation-extraction.md §6, §7
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.services.llm.adapter import get_adapter
from app.services.ontology.prompts import SCHEMA_REMINDER
from app.services.ontology.schemas import ExtractedRelation, ExtractionBatch

if TYPE_CHECKING:
    from app.services.llm.adapter import LLMAdapter

logger = logging.getLogger(__name__)

# Soft cap on body size. SEC 8-K Item 1.01 본문 + signatures가 평균 ~6-12K chars.
# 한국어는 약 1 char/token, 영어 ~0.25 char/token. 12K → ~4.5K tokens (영어).
_BODY_TOKEN_BUDGET = 12000
_MAX_RETRIES = 1


async def extract_relations(
    body: str,
    *,
    prompt_template: str,
    source_url: str | None = None,
    adapter: "LLMAdapter | None" = None,
    prompt_kwargs: dict | None = None,
) -> list[ExtractedRelation]:
    """Run one body through the LLM and return validated relations.

    Empty / very short body → [] (no LLM call).
    Body longer than _BODY_TOKEN_BUDGET → truncate (chunking deferred to v2+).
    `prompt_kwargs` is merged into `prompt_template.format(body=..., **kwargs)` so
    callers can inject focal_ticker / focal_name etc into the prompt.
    """
    if not body or len(body.strip()) < 50:
        return []

    truncated = body[:_BODY_TOKEN_BUDGET]
    adapter = adapter or get_adapter()

    relations = await _call_with_retry(
        adapter, prompt_template, truncated, prompt_kwargs or {}
    )
    if source_url:
        for rel in relations:
            rel.extra_metadata.setdefault("source_url", source_url)
    return relations


async def _call_with_retry(
    adapter: "LLMAdapter", prompt_template: str, body: str, prompt_kwargs: dict
) -> list[ExtractedRelation]:
    last_error: str | None = None
    for attempt in range(_MAX_RETRIES + 1):
        prompt = prompt_template.format(body=body, **prompt_kwargs)
        if attempt > 0:
            prompt += SCHEMA_REMINDER
        try:
            raw = await adapter.generate_json(prompt)
        except Exception as e:  # noqa: BLE001 — adapter can raise on transport
            last_error = f"adapter call failed: {e}"
            logger.warning("extract_relations attempt %d: %s", attempt, last_error)
            continue

        parsed = _parse_response(raw)
        if parsed is not None:
            try:
                return ExtractionBatch(relations=parsed).relations
            except ValidationError as e:
                last_error = f"validation: {e.errors()[:3]}"
                logger.info("extract_relations attempt %d validation: %s", attempt, last_error)
                continue
        last_error = "json parse failed"

    logger.warning("extract_relations gave up after %d attempts: %s", _MAX_RETRIES + 1, last_error)
    return []


def _parse_response(raw: str) -> list[dict] | None:
    """Tolerate either a bare JSON array or a `{"relations": [...]}` wrapper."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Strip code-fence if model emitted ```json ... ```
        if text.startswith("```"):
            text = text.strip("`").lstrip("json").strip()
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return None
        else:
            return None

    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict) and isinstance(parsed.get("relations"), list):
        return parsed["relations"]
    return None
