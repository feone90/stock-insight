"""v2 analysis engine — research → (data || analyst) → compose → persist.

Pipeline (after the refactor):
1. `is_analyzable` fail-fast (called by API; engine repeats defensively)
2. Per-ticker `asyncio.Lock` serializes concurrent analyze() calls
3. `run_research` (Stage 1) — cheap LLM with tools
4. `asyncio.gather(assemble_data_layer, run_synthesize)` — data + analyst in parallel
5. `compose` — merges layers, remaps citation IDs, server-injects identity, validates
6. Persist to `analyses` (schema_version='v2'); Phase A v1 rows preserved
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date as _date
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.database import async_session
from app.models import PriceHistory, Stock
from app.models.analysis import Analysis
from app.schemas.card import (
    AnalystOutput,
    Catalyst,
    Citation,
    Claim,
    DataLayer,
    Decision,
    Fundamentals,
    GlanceVerdict,
    Interpretation,
    MacroContext,
    Relation,
    RelationsSummary,
    StockCard,
    TechMomentum,
    Thesis,
)
from app.services.analyst.data_layer import (
    assemble_data_layer,
    fetch_stock_identity,
)
from app.services.analyst.persona import PERSONA_VERSION
from app.services.analyst.research import run_research
from app.services.analyst.synthesize import run_synthesize

logger = logging.getLogger(__name__)

# Per-ticker locks for concurrent analyze() safety. In-memory, single-process.
_TICKER_LOCKS: dict[str, asyncio.Lock] = {}
_LOCKS_GUARD = asyncio.Lock()


async def _get_ticker_lock(ticker: str) -> asyncio.Lock:
    """Lazily create + return the lock for `ticker`."""
    async with _LOCKS_GUARD:
        if ticker not in _TICKER_LOCKS:
            _TICKER_LOCKS[ticker] = asyncio.Lock()
        return _TICKER_LOCKS[ticker]


# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------


async def is_analyzable(ticker: str) -> tuple[bool, str | None]:
    """Cheap pre-check; safe to call from the API request thread.

    Returns (False, reason) when the engine should NOT run for this ticker:
      - stock not in DB
      - current_price <= 0
      - 0 price-history rows
    """
    ticker = ticker.strip().upper()
    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            return False, "stock not found"
        if (stock.current_price or 0) <= 0:
            return False, "current_price <= 0"
        rows = (
            await db.execute(
                select(func.count())
                .select_from(PriceHistory)
                .where(PriceHistory.stock_id == stock.id)
            )
        ).scalar() or 0
        if rows == 0:
            return False, "no price history"
        return True, None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def analyze(ticker: str) -> StockCard:
    """Run full v2 pipeline and persist. Returns the StockCard.

    Concurrent calls for the same ticker serialize on a per-ticker lock.
    """
    ticker = ticker.strip().upper()

    ok, reason = await is_analyzable(ticker)
    if not ok:
        raise ValueError(f"analyze[{ticker}]: not analyzable — {reason}")

    lock = await _get_ticker_lock(ticker)
    async with lock:
        return await _run_locked(ticker)


async def _run_locked(ticker: str) -> StockCard:
    logger.info("analyze[%s]: stage 1 research starting", ticker)
    research = await run_research(ticker)

    logger.info("analyze[%s]: stage 2 data + analyst in parallel", ticker)
    data, analyst = await asyncio.gather(
        assemble_data_layer(ticker),
        run_synthesize(ticker, research),
    )

    identity = await fetch_stock_identity(ticker)
    card = compose(ticker, data, analyst, identity)

    await _persist(ticker, card)
    logger.info("analyze[%s]: done", ticker)
    return card


# ---------------------------------------------------------------------------
# Compose — merges DataLayer + AnalystOutput → StockCard
# ---------------------------------------------------------------------------


def compose(
    ticker: str,
    data: DataLayer,
    analyst: AnalystOutput,
    identity: dict,
) -> StockCard:
    """Single source of truth for layer reconciliation.

    - Server fields (ticker, name, market, price, asof) come from `identity`,
      injected last so they always win over anything the LLM produced.
    - Final citation pool: `data.data_citations` (unchanged) +
      offset(`analyst.interp_citations`, +K). Every citation ID referenced
      by any nested field is validated against the final pool.
    - `RelationsSummary` is built from `data.relations_data` (structure)
      overlaid with `analyst.relations_narrative` (one_line + per-target notes).
    - Missing data sections (e.g. < 30 days history → `data.technical=None`)
      become structural stubs so the StockCard contract still holds.
    """
    k = len(data.data_citations)

    # Final citation pool: data IDs unchanged 1..K; analyst IDs offset by K.
    final_citations: list[Citation] = list(data.data_citations)
    for c in analyst.interp_citations:
        final_citations.append(
            Citation(
                id=c.id + k,
                source_type=c.source_type,
                label=c.label,
                url=c.url,
                timestamp=c.timestamp,
            )
        )

    glance = GlanceVerdict(
        final_grade=analyst.glance.final_grade,
        grade_delta=analyst.glance.grade_delta,
        stance=analyst.glance.stance,
        entry_stage=analyst.glance.entry_stage,
        one_line=analyst.glance.one_line,
        citations=_shift_ids(analyst.glance.citations, k),
    )

    thesis = Thesis(
        core_thesis=analyst.thesis.core_thesis,
        supports=[_shift_claim(c, k) for c in analyst.thesis.supports],
        opposes=[_shift_claim(c, k) for c in analyst.thesis.opposes],
        catalysts=[_shift_catalyst(cat, k) for cat in analyst.thesis.catalysts],
        no_catalysts_reason=analyst.thesis.no_catalysts_reason,
        scenarios=list(analyst.thesis.scenarios),
        citations=_shift_ids(analyst.thesis.citations, k),
    )

    decision = Decision(
        stance=analyst.decision.stance,
        sizing_note=analyst.decision.sizing_note,
        support_price=analyst.decision.support_price,
        risk_threshold=analyst.decision.risk_threshold,
        note=analyst.decision.note,
        citations=_shift_ids(analyst.decision.citations, k),
        interpretation=_shift_interp(analyst.decision.interpretation, k),
    )

    relations_with_notes: list[Relation] = []
    for rel in data.relations_data:
        narrative_note = analyst.relations_narrative.notes_by_target.get(
            rel.target_ticker, rel.notes
        )
        relations_with_notes.append(
            Relation(
                target_ticker=rel.target_ticker,
                target_name=rel.target_name,
                relation_type=rel.relation_type,
                strength=rel.strength,
                today_change_pct=rel.today_change_pct,
                notes=narrative_note,
                citation_ids=list(rel.citation_ids),  # data pool, no shift
                # P1.6 v0+ — discovery + signal expressiveness pass-through.
                signal_direction=rel.signal_direction,
                confidence=rel.confidence,
                source=rel.source,
                source_url=rel.source_url,
                valid_from=rel.valid_from,
                valid_until=rel.valid_until,
            )
        )

    relations = RelationsSummary(
        one_line=analyst.relations_narrative.one_line,
        relations=relations_with_notes,
        citations=_shift_ids(analyst.relations_narrative.citations, k),
    )

    technical = data.technical or _stub_technical()
    macro = data.macro or _stub_macro()
    fundamentals = data.fundamentals or Fundamentals()
    news = list(data.news)

    valid_ids = {c.id for c in final_citations}
    _validate_citation_refs(
        glance=glance,
        thesis=thesis,
        decision=decision,
        relations=relations,
        technical=technical,
        macro=macro,
        fundamentals=fundamentals,
        news=news,
        valid_ids=valid_ids,
    )

    return StockCard(
        ticker=identity.get("ticker", ticker),
        name_ko=identity.get("name_ko", ""),
        name_en=identity.get("name_en", ""),
        market=identity.get("market", ""),
        sector=identity.get("sector", ""),
        tags=identity.get("tags", []),
        price=identity.get("price", 0.0),
        change=identity.get("change", 0.0),
        change_pct=identity.get("change_pct", 0.0),
        asof=identity.get("asof"),
        glance=glance,
        thesis=thesis,
        technical=technical,
        relations=relations,
        news=news,
        political_signals=data.political_signals,
        macro=macro,
        fundamentals=fundamentals,
        decision=decision,
        citations=final_citations,
        analysis_id=str(uuid.uuid4()),
        generated_at=datetime.now(timezone.utc),
        persona_version=PERSONA_VERSION,
        schema_version="v2",
    )


# ---------------------------------------------------------------------------
# Compose helpers
# ---------------------------------------------------------------------------


def _shift_ids(ids: list[int], offset: int) -> list[int]:
    return [i + offset for i in ids]


def _shift_interp(
    interp: Interpretation | None, offset: int
) -> Interpretation | None:
    if interp is None:
        return None
    return Interpretation(
        kind=interp.kind,
        based_on=_shift_ids(interp.based_on, offset),
        rationale=interp.rationale,
    )


def _shift_claim(c: Claim, offset: int) -> Claim:
    return Claim(
        text=c.text,
        citations=_shift_ids(c.citations, offset),
        interpretation=_shift_interp(c.interpretation, offset),
    )


def _shift_catalyst(cat: Catalyst, offset: int) -> Catalyst:
    return Catalyst(
        when=cat.when,
        event=cat.event,
        impact_estimate=cat.impact_estimate,
        direction=cat.direction,
        citation_ids=_shift_ids(cat.citation_ids, offset),
    )


def _stub_technical() -> TechMomentum:
    return TechMomentum(
        rsi_14=None,
        mfi_14=None,
        atr_pct=None,
        cmf_20=None,
        obv_ratio=None,
        ma_stack=None,
        rvol_20=None,
        box_position=None,
        summary_line="지표 데이터 부족",
        citations=[],
    )


def _stub_macro() -> MacroContext:
    return MacroContext(
        one_line="매크로 데이터 미수집",
        vix=None,
        fx_pairs={},
        us_10y=None,
        sensitivities=[],
        upcoming_events=[],
        citations=[],
    )


def _validate_citation_refs(
    *,
    glance: GlanceVerdict,
    thesis: Thesis,
    decision: Decision,
    relations: RelationsSummary,
    technical: TechMomentum,
    macro: MacroContext,
    fundamentals: Fundamentals,
    news: list,
    valid_ids: set[int],
) -> None:
    def _check(ids: list[int], where: str) -> None:
        for cid in ids:
            if cid not in valid_ids:
                raise ValueError(
                    f"compose: citation id {cid} (in {where}) not in final pool"
                )

    _check(glance.citations, "glance")
    _check(thesis.citations, "thesis")
    for i, c in enumerate(thesis.supports):
        _check(c.citations, f"thesis.supports[{i}]")
        if c.interpretation:
            _check(c.interpretation.based_on, f"thesis.supports[{i}].interp")
    for i, c in enumerate(thesis.opposes):
        _check(c.citations, f"thesis.opposes[{i}]")
        if c.interpretation:
            _check(c.interpretation.based_on, f"thesis.opposes[{i}].interp")
    for i, cat in enumerate(thesis.catalysts):
        _check(cat.citation_ids, f"thesis.catalysts[{i}]")
    _check(decision.citations, "decision")
    if decision.interpretation:
        _check(decision.interpretation.based_on, "decision.interp")
    _check(relations.citations, "relations")
    for i, rel in enumerate(relations.relations):
        _check(rel.citation_ids, f"relations.relations[{i}]")
    _check(technical.citations, "technical")
    if technical.interpretation:
        _check(technical.interpretation.based_on, "technical.interp")
    _check(macro.citations, "macro")
    _check(fundamentals.citations, "fundamentals")
    for i, n in enumerate(news):
        if n.citation_id not in valid_ids:
            raise ValueError(
                f"compose: news[{i}].citation_id {n.citation_id} not in final pool"
            )


# ---------------------------------------------------------------------------
# Persistence — Phase A v1 rows preserved via schema_version discriminator
# ---------------------------------------------------------------------------


async def _persist(ticker: str, card: StockCard) -> None:
    """Upsert into `analyses` (one row per stock+date+period — DB unique).

    A Phase A v1 row for the same day gets its `schema_version` bumped to v2
    and `card_data` populated; its KeywordDetail children are not touched
    (cascade is delete-orphan, only fires on Analysis delete).
    """
    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            logger.error("persist[%s]: stock disappeared mid-flight", ticker)
            return

        today = _date.today()
        card_json = card.model_dump(mode="json")
        existing = (
            await db.execute(
                select(Analysis).where(
                    Analysis.stock_id == stock.id,
                    Analysis.date == today,
                    Analysis.period_type == "daily",
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.summary = card.glance.one_line[:500]
            existing.feedback = card.thesis.core_thesis[:1000]
            existing.schema_version = "v2"
            existing.card_data = card_json
            existing.persona_version = card.persona_version
        else:
            db.add(
                Analysis(
                    stock_id=stock.id,
                    date=today,
                    period_type="daily",
                    summary=card.glance.one_line[:500],
                    feedback=card.thesis.core_thesis[:1000],
                    schema_version="v2",
                    card_data=card_json,
                    persona_version=card.persona_version,
                )
            )
        await db.commit()
