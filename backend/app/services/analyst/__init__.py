"""v2 analyst engine — research + data layer + synthesizer + compose.

Public exports:
    get_analyst_adapter — common factory used by every analyst module.
        Tests monkeypatch the per-module re-import (e.g.
        `app.services.analyst.synthesize.get_analyst_adapter`).
"""
from __future__ import annotations

from app.services.llm.adapter import LLMAdapter, get_adapter


def get_analyst_adapter() -> LLMAdapter:
    """Single source of truth for analyst-side LLM adapter selection.

    Provider is config-driven (`settings.llm_provider`). Each analyst module
    imports this name; tests monkeypatch the imported name on the consuming
    module so per-module mocks stay isolated.
    """
    return get_adapter()


__all__ = ["get_analyst_adapter"]
