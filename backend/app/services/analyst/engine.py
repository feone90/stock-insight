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
    interp_ids_pre_shift = {c.id for c in analyst.interp_citations}

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
        citations=_resolve_ids(
            analyst.glance.citations, k=k,
            interp_ids_pre_shift=interp_ids_pre_shift, where="glance",
        ),
    )

    thesis = Thesis(
        core_thesis=analyst.thesis.core_thesis,
        supports=[
            _resolve_claim(c, k=k, interp_ids_pre_shift=interp_ids_pre_shift,
                           where=f"thesis.supports[{i}]")
            for i, c in enumerate(analyst.thesis.supports)
        ],
        opposes=[
            _resolve_claim(c, k=k, interp_ids_pre_shift=interp_ids_pre_shift,
                           where=f"thesis.opposes[{i}]")
            for i, c in enumerate(analyst.thesis.opposes)
        ],
        catalysts=[
            _resolve_catalyst(cat, k=k, interp_ids_pre_shift=interp_ids_pre_shift,
                              where=f"thesis.catalysts[{i}]")
            for i, cat in enumerate(analyst.thesis.catalysts)
        ],
        no_catalysts_reason=analyst.thesis.no_catalysts_reason,
        scenarios=list(analyst.thesis.scenarios),
        citations=_resolve_ids(
            analyst.thesis.citations, k=k,
            interp_ids_pre_shift=interp_ids_pre_shift, where="thesis",
        ),
    )

    decision = Decision(
        stance=analyst.decision.stance,
        sizing_note=analyst.decision.sizing_note,
        support_price=analyst.decision.support_price,
        risk_threshold=analyst.decision.risk_threshold,
        note=analyst.decision.note,
        citations=_resolve_ids(
            analyst.decision.citations, k=k,
            interp_ids_pre_shift=interp_ids_pre_shift, where="decision",
        ),
        interpretation=_resolve_interp(
            analyst.decision.interpretation, k=k,
            interp_ids_pre_shift=interp_ids_pre_shift, where="decision.interp",
        ),
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
        citations=_resolve_ids(
            analyst.relations_narrative.citations, k=k,
            interp_ids_pre_shift=interp_ids_pre_shift, where="relations_narrative",
        ),
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


def _resolve_ids(
    ids: list[int],
    *,
    k: int,
    interp_ids_pre_shift: set[int],
    where: str,
) -> list[int]:
    """LLM 이 출력한 citation id 를 final pool 기준으로 매핑.

    LLM 은 data_citations (1..K) 와 자기 interp_citations (1..M) 가 모두 1 부터
    시작한다는 사실을 모른다. 그래서 LLM 이 cite 한 id 가 양쪽 풀에 동시에
    존재하는 케이스 (예: interp 1 등록 + data 1 도 존재) 가 자주 발생하고,
    어느 쪽을 의도했는지 시스템 입장에서는 결정 불가능하다 (Codex 리뷰 high).

    네 경우:
      (a) id ∈ interp AND id ∈ data 범위(1..K)  → ambiguous → drop + log
      (b) id ∈ interp 만                         → +K shift (LLM 등록 출처)
      (c) 1 ≤ id ≤ K 만                          → 그대로 유지 (data 차용)
      (d) 어디에도 없음                          → drop + log (LLM hallucination)
    """
    resolved: list[int] = []
    dropped_dangling: list[int] = []
    dropped_ambiguous: list[int] = []
    for i in ids:
        in_interp = i in interp_ids_pre_shift
        in_data = 1 <= i <= k
        if in_interp and in_data:
            dropped_ambiguous.append(i)
        elif in_interp:
            resolved.append(i + k)
        elif in_data:
            resolved.append(i)
        else:
            dropped_dangling.append(i)
    if dropped_ambiguous:
        logger.warning(
            "compose: dropped %d ambiguous citation id(s) in %s: %s "
            "(both interp and data pool — cannot disambiguate; k=%d interp=%s)",
            len(dropped_ambiguous), where, dropped_ambiguous, k,
            sorted(interp_ids_pre_shift),
        )
    if dropped_dangling:
        logger.info(
            "compose: dropped %d dangling citation id(s) in %s: %s (k=%d interp=%s)",
            len(dropped_dangling), where, dropped_dangling, k,
            sorted(interp_ids_pre_shift),
        )
    return resolved


def _resolve_interp(
    interp: Interpretation | None,
    *,
    k: int,
    interp_ids_pre_shift: set[int],
    where: str,
) -> Interpretation | None:
    if interp is None:
        return None
    return Interpretation(
        kind=interp.kind,
        based_on=_resolve_ids(
            interp.based_on, k=k, interp_ids_pre_shift=interp_ids_pre_shift,
            where=f"{where}.based_on",
        ),
        rationale=interp.rationale,
    )


def _resolve_claim(
    c: Claim,
    *,
    k: int,
    interp_ids_pre_shift: set[int],
    where: str,
) -> Claim:
    return Claim(
        text=c.text,
        citations=_resolve_ids(
            c.citations, k=k, interp_ids_pre_shift=interp_ids_pre_shift,
            where=f"{where}.citations",
        ),
        interpretation=_resolve_interp(
            c.interpretation, k=k, interp_ids_pre_shift=interp_ids_pre_shift,
            where=f"{where}.interp",
        ),
    )


def _resolve_catalyst(
    cat: Catalyst,
    *,
    k: int,
    interp_ids_pre_shift: set[int],
    where: str,
) -> Catalyst:
    return Catalyst(
        when=cat.when,
        event=cat.event,
        impact_estimate=cat.impact_estimate,
        direction=cat.direction,
        citation_ids=_resolve_ids(
            cat.citation_ids, k=k, interp_ids_pre_shift=interp_ids_pre_shift,
            where=f"{where}.citation_ids",
        ),
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
    """Race-safe upsert into `analyses` keyed on `uq_analysis_stock_date_period`.

    Codex review [medium]: previous select-then-insert could race — two
    concurrent analyze() runs for the same ticker on the same day could both
    miss the existence check and one would die on the unique constraint.
    Now: if a row exists, mutate via ORM (preserves Phase A keyword children +
    identity-map sync); if not, INSERT ON CONFLICT DO NOTHING; on conflict
    (race tail), re-select and mutate the racer's row.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    async with async_session() as db:
        stock = (
            await db.execute(select(Stock).where(Stock.ticker == ticker))
        ).scalar_one_or_none()
        if not stock:
            logger.error("persist[%s]: stock disappeared mid-flight", ticker)
            return

        today = _date.today()
        card_json = card.model_dump(mode="json")
        summary = card.glance.one_line[:500]
        feedback = card.thesis.core_thesis[:1000]

        def _apply(row: Analysis) -> None:
            row.summary = summary
            row.feedback = feedback
            row.schema_version = "v2"
            row.card_data = card_json
            row.persona_version = card.persona_version

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
            _apply(existing)
            await db.commit()
            return

        stmt = (
            pg_insert(Analysis)
            .values(
                stock_id=stock.id,
                date=today,
                period_type="daily",
                summary=summary,
                feedback=feedback,
                schema_version="v2",
                card_data=card_json,
                persona_version=card.persona_version,
            )
            .on_conflict_do_nothing(constraint="uq_analysis_stock_date_period")
        )
        result = await db.execute(stmt)
        await db.commit()
        if (result.rowcount or 0) == 0:
            # Race tail — another analyze() got the row in between our SELECT
            # and INSERT. Re-fetch and mutate so our card_data isn't lost.
            racer = (
                await db.execute(
                    select(Analysis).where(
                        Analysis.stock_id == stock.id,
                        Analysis.date == today,
                        Analysis.period_type == "daily",
                    )
                )
            ).scalar_one()
            _apply(racer)
            await db.commit()
