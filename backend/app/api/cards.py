"""v2 card endpoints: GET card / POST analyze / POST refresh (with cooldown).

가족 dev 환경 self-heal:
  - `is_analyzable` fail 사유가 'no price history'면 즉시 sync_prices 호출.
  - analyzable 이라도 Financial row 없거나 News 가 5건 미만이면 보강 sync.
  - analyze 트리거 시 ontology news extraction 도 같이 background 실행.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.disclosure import sync_disclosures
from app.collectors.financials import sync_financials
from app.collectors.news import sync_news
from app.collectors.stock_price import sync_prices
from app.config import settings
from app.database import async_session, get_db
from app.dependencies import get_stock_or_404
from app.models import News, PriceHistory, RefreshCooldown, Stock
from app.models.analysis import Analysis
from app.schemas.card_history import AnalysisHistoryResponse, StockEventsResponse
from app.models.financial import Financial
from app.services.analyst.cost import can_proceed
from app.services.analyst.engine import analyze, is_analyzable
from app.services.analyst.history import build_analysis_history, build_event_markers
from app.services.ontology import extract_news_relations_for_ticker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stocks", tags=["cards"])


async def _try_acquire_cooldown(
    db: AsyncSession, ticker: str, action: str, cooldown_s: int
) -> tuple[bool, int]:
    """DB-backed atomic cooldown — multi-worker safe.

    옛 in-memory `_last_*: dict` 는 gunicorn worker 별 분리되어 production
    correctness 없음. 이 헬퍼는 `INSERT ... ON CONFLICT DO UPDATE WHERE` 한
    번으로 acquire 시도 + 잔여 시간 반환.

    Returns:
        (True, 0) — 잠금 획득, last_at 새로 박힘. 호출자는 작업 진행.
        (False, remaining_seconds) — 아직 cooldown 중. 429 반환 권장.
    """
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    now = _dt.utcnow()
    cutoff = now - _td(seconds=cooldown_s)
    key = ticker.upper()

    stmt = (
        pg_insert(RefreshCooldown)
        .values(ticker=key, action=action, last_at=now)
        .on_conflict_do_update(
            index_elements=["ticker", "action"],
            set_={"last_at": now},
            where=(RefreshCooldown.last_at < cutoff),
        )
        .returning(RefreshCooldown.last_at)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        # ON CONFLICT 발동했지만 WHERE 조건 (last_at < cutoff) 미충족 →
        # 옛 last_at 그대로. 별도 query 로 잔여 계산.
        existing = (
            await db.execute(
                select(RefreshCooldown.last_at).where(
                    RefreshCooldown.ticker == key,
                    RefreshCooldown.action == action,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            # 이론적으로 발생 안 함 (acquire 했어야 함). race 안전을 위해 허용.
            await db.commit()
            return True, 0
        remaining = int(cooldown_s - (now - existing).total_seconds())
        return False, max(1, remaining)
    await db.commit()
    return True, 0


_MIN_NEWS_FOR_ANALYZE = 5


async def _ensure_analyzable(
    ticker: str, stock: Stock, db: AsyncSession
) -> tuple[bool, str | None]:
    """`is_analyzable` 체크 + 데이터 stale 여부 검사.

    self-heal 트리거 조건:
      1. is_analyzable fail (no price history / current_price <= 0)
      2. Financial row 없음 (PER/PBR/매출 비어있는 카드 방지)
      3. News 5건 미만 (한 줄 요약이라도 LLM 이 만들 만한 input 보장)

    handler 의 `db` 세션을 그대로 재사용해야 stock object detach 안 됨.
    """
    ok, reason = await is_analyzable(ticker)

    needs_sync = False
    sync_reason = reason
    if not ok and reason in ("no price history", "current_price <= 0"):
        needs_sync = True
    elif ok:
        fin_count = (
            await db.execute(
                select(func.count()).select_from(Financial).where(
                    Financial.stock_id == stock.id
                )
            )
        ).scalar() or 0
        news_count = (
            await db.execute(
                select(func.count()).select_from(News).where(
                    News.stock_id == stock.id
                )
            )
        ).scalar() or 0
        if fin_count == 0 or news_count < _MIN_NEWS_FOR_ANALYZE:
            needs_sync = True
            sync_reason = f"stale (fin={fin_count} news={news_count})"

    if needs_sync:
        logger.info("self-heal sync for %s (reason=%s)", ticker, sync_reason)
        try:
            await sync_prices(db, stock)
            await sync_news(db, stock)
            await sync_financials(db, stock)
            await sync_disclosures(db, stock)
        except Exception as e:  # noqa: BLE001
            logger.exception("self-heal failed for %s: %s", ticker, e)
            return False, f"self-heal failed: {e}"
        ok, reason = await is_analyzable(ticker)
    return ok, reason


async def _extract_relations_safe(ticker: str) -> None:
    """analyze 와 같이 background 에서 도는 ontology 추출. budget/실패는 swallow.

    가족 환경 — 새로 본 종목이면 analyze 직후 supply-chain/competitor 관계도
    당일치 뉴스에서 한 번 채워줘야 사용자가 카드 다시 안 열어도 됨.

    Window 는 admin force-extract 와 동일한 14일 / 10 articles. 짧은 윈도우
    (7일/5건) 로는 mid-cap KR 종목에서 LLM 이 충분한 entity context 못 받아
    관계 0건 반환하는 케이스가 다수 (240810 원익IPS, 042700 한미반도체 검증됨).
    """
    if not can_proceed():
        logger.info("ontology extract skipped for %s: budget", ticker)
        return
    try:
        summary = await extract_news_relations_for_ticker(
            ticker,
            since=date.today() - timedelta(days=14),
            articles_per_run=10,
        )
        logger.info(
            "ontology extract %s: seen=%s short=%s llm=%s upserted=%s buffered=%s",
            ticker,
            summary.get("articles_seen"),
            summary.get("articles_skipped_short"),
            summary.get("llm_relations_returned"),
            summary.get("upserted"),
            summary.get("buffered"),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("ontology extract failed for %s: %s", ticker, e)


@router.get("/{ticker}/card")
async def get_card(
    ticker: str,
    stock: Stock = Depends(get_stock_or_404),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(Analysis)
            .where(
                Analysis.stock_id == stock.id,
                Analysis.schema_version == "v2",
            )
            .order_by(Analysis.date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if not row or not row.card_data:
        raise HTTPException(
            status_code=404,
            detail=f"v2 card for {ticker.upper()} not yet generated. POST /analyze first.",
        )

    # 2026-05-14: Per-layer freshness overlay. card_data JSONB 는 analyze()
    # 실행 시점 스냅샷. 그 후 sync_prices / sync_news 가 새 row 박아도 JSON
    # 안의 price/change/asof/price_asof/news_latest_at 옛 값 — 카드 헤더에
    # 옛 가격, 옛 시각, 관계 카드의 화살표 % 까지 stale.
    # 2026-05-15: price/change/change_pct/asof + relations 의 target
    # today_change_pct 까지 overlay 확장 — analyze 안 다시 돌려도 카드 표면
    # fresh. card_data 본체는 안 건드림.
    card = dict(row.card_data)

    # 1) 헤더 가격 — get_stock_or_404 가 이미 fresh Stock row 줌.
    card["price"] = stock.current_price or 0.0
    card["change"] = stock.change or 0.0
    card["change_pct"] = stock.change_percent or 0.0
    card["asof"] = datetime.now(timezone.utc).isoformat()

    # 2) Per-layer 마지막 갱신 시각.
    # price_asof: stock.last_price_sync_at (sync_prices 호출 *시각*) 우선,
    # fallback MAX(PriceHistory.date). 시각이라야 같은 날 새로고침 시
    # frontend polling 이 advance 감지해 "방금 전" 표시.
    #
    # 2026-05-15 timezone bug fix — DB DateTime 컬럼은 naive (tzinfo 없음).
    # naive datetime.isoformat() = "2026-05-15T05:00:00" (Z/offset 없음) →
    # frontend `new Date(...)` 가 *local time (KST)* 로 parse → 9 시간 offset
    # 어긋남 ("9시간 전" 표시). UTC 명시 → frontend KST 환경에서 정확.
    def _to_utc_iso(dt):
        if dt is None:
            return None
        if hasattr(dt, "tzinfo") and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)

    if stock.last_price_sync_at is not None:
        card["price_asof"] = _to_utc_iso(stock.last_price_sync_at)
    else:
        price_max = (
            await db.execute(
                select(func.max(PriceHistory.date)).where(
                    PriceHistory.stock_id == stock.id
                )
            )
        ).scalar()
        if price_max is not None:
            card["price_asof"] = _to_utc_iso(price_max)
    news_max = (
        await db.execute(
            select(func.max(News.published_at)).where(News.stock_id == stock.id)
        )
    ).scalar()
    if news_max is not None:
        card["news_latest_at"] = _to_utc_iso(news_max)

    # 3) 관계 카드의 target today_change_pct — 각 target ticker 의 현재
    # change_percent. 한 번에 batch lookup.
    relations_payload = (card.get("relations") or {}).get("relations") or []
    target_tickers = [
        r.get("target_ticker") for r in relations_payload if r.get("target_ticker")
    ]
    if target_tickers:
        target_rows = (
            await db.execute(
                select(Stock.ticker, Stock.change_percent).where(
                    Stock.ticker.in_(target_tickers)
                )
            )
        ).all()
        change_map = {t: cp for t, cp in target_rows}
        for r in relations_payload:
            t = r.get("target_ticker")
            if t in change_map:
                r["today_change_pct"] = change_map[t]

    return card


@router.get("/{ticker}/card/history", response_model=AnalysisHistoryResponse)
async def get_card_history(
    ticker: str,
    limit: int = 14,
    stock: Stock = Depends(get_stock_or_404),
    db: AsyncSession = Depends(get_db),
):
    """Daily card archive — stock memory for previous AI decisions.

    Phase 1 intentionally reuses `analyses.card_data` snapshots so old cards
    remain useful without a DB migration. Frontend uses this to show "what
    changed since yesterday" instead of losing prior reasoning on each refresh.
    """
    safe_limit = max(1, min(limit, 60))
    rows = (
        await db.execute(
            select(Analysis)
            .where(
                Analysis.stock_id == stock.id,
                Analysis.schema_version == "v2",
                Analysis.card_data.is_not(None),
            )
            .order_by(Analysis.date.desc())
            .limit(safe_limit)
        )
    ).scalars().all()
    return AnalysisHistoryResponse(
        ticker=ticker.upper(),
        items=build_analysis_history(list(rows)),
    )


@router.get("/{ticker}/events", response_model=StockEventsResponse)
async def get_stock_events(
    ticker: str,
    days: int = 365,
    limit: int = 80,
    stock: Stock = Depends(get_stock_or_404),
    db: AsyncSession = Depends(get_db),
):
    """Chart event markers extracted from previous daily cards."""
    safe_days = max(7, min(days, 730))
    safe_limit = max(1, min(limit, 200))
    since = date.today() - timedelta(days=safe_days)
    rows = (
        await db.execute(
            select(Analysis)
            .where(
                Analysis.stock_id == stock.id,
                Analysis.schema_version == "v2",
                Analysis.card_data.is_not(None),
                Analysis.date >= since,
            )
            .order_by(Analysis.date.desc())
            .limit(safe_days)
        )
    ).scalars().all()
    return StockEventsResponse(
        ticker=ticker.upper(),
        events=build_event_markers(list(rows), limit=safe_limit),
    )


@router.post("/{ticker}/analyze", status_code=202)
async def trigger_analyze(
    ticker: str,
    bg: BackgroundTasks,
    stock: Stock = Depends(get_stock_or_404),
    db: AsyncSession = Depends(get_db),
):
    if not can_proceed():
        raise HTTPException(503, "daily analysis budget exceeded")
    ok, reason = await _ensure_analyzable(ticker, stock, db)
    if not ok:
        raise HTTPException(422, f"not analyzable: {reason}")
    bg.add_task(analyze, ticker)
    bg.add_task(_extract_relations_safe, ticker)
    return {"status": "queued", "ticker": ticker.upper()}


# 3-way refresh split (2026-05-14, user 피드백 + Codex 시니어 리뷰).
# "데이터 새로고침" 한 버튼에 가격/뉴스/재무/공시 + smart analyze 까지 묶어
# 두니 (a) 라벨이 모호하고 (b) "주가만 새로고침" 이 외부 API 4-5 개 다 도느라
# 늘리고 (c) "언제 갱신됐는지" 가 통째로만 표시돼 사용자가 가격이 fresh 인지
# 뉴스가 fresh 인지 분간 못 함. → 각 layer 자기 cooldown + 자기 timestamp.
_PRICE_REFRESH_COOLDOWN_S = 30  # 30s — 가격은 가벼움. 클릭 즉시 fresh quote.
_DATA_REFRESH_COOLDOWN_S = 120  # 2분 — 뉴스/공시는 외부 API 무거움. 가족 5명
# 새로고침 갈겨도 외부 rate-limit 보호.


@router.post("/{ticker}/price_refresh", status_code=202)
async def price_refresh(
    ticker: str,
    bg: BackgroundTasks,
    stock: Stock = Depends(get_stock_or_404),
    db: AsyncSession = Depends(get_db),
):
    """가격만 동기화 — sync_prices 1개 콜렉터. LLM 0, 외부 API 1개.

    2026-05-14 사용자 통찰: "주가만 새로고침하면 더 빨라야 하는데 늦어 —
    불필요한 작업하고있는거 아니야?". 옛 `data_refresh` 는 sync_prices +
    sync_news + sync_financials + sync_disclosures 를 직렬로 돌려서 가격
    하나 갱신에 외부 API 4-5 곳을 두드렸다. 가격은 가장 빨리 변하고 (1-2 분),
    가장 가볍게 (yfinance 1 콜) 받을 수 있어야 한다.

    효과 (즉시): 차트·헤더 가격 endpoint (`GET /prices`, `GET /stocks/{ticker}`)
    가 매번 fresh DB query → 이 엔드포인트 호출 직후 즉시 새 가격 + price_asof
    노출.

    30s cooldown — 외부 yfinance rate limit + 가족이 무지성 클릭해도 안전.
    """
    key = ticker.upper()
    ok_cd, remaining = await _try_acquire_cooldown(
        db, ticker, "price", _PRICE_REFRESH_COOLDOWN_S
    )
    if not ok_cd:
        raise HTTPException(429, f"cooldown: try again in {remaining}s")

    async def _sync_price_only() -> None:
        async with async_session() as own_db:
            fresh = (
                await own_db.execute(
                    select(Stock).where(Stock.ticker == ticker)
                )
            ).scalar_one_or_none()
            if not fresh:
                return
            try:
                await sync_prices(own_db, fresh)
            except Exception as e:  # noqa: BLE001
                logger.warning("price_refresh %s sync_prices failed: %s", ticker, e)

    bg.add_task(_sync_price_only)
    return {"status": "price_refresh_queued", "ticker": key}


@router.post("/{ticker}/data_refresh", status_code=202)
async def data_refresh(
    ticker: str,
    bg: BackgroundTasks,
    stock: Stock = Depends(get_stock_or_404),
    db: AsyncSession = Depends(get_db),
):
    """뉴스·공시 동기화 + 새 뉴스 임계치 도달 시 AI narrative 자동 재생성.

    2026-05-14 split: 가격(별도 `/price_refresh`) 과 재무(분기 단위 → 야간 cron)
    는 빠짐. 이 엔드포인트가 책임지는 layer:
      - News (sync_news)
      - 공시 (sync_disclosures)
      - smart-trigger: 마지막 카드 생성 시점 이후 새 뉴스 ≥ 2건이면 `analyze()`
        자동 호출 (의견 자체가 바뀔만한 trigger 일 때만 LLM $0.25 지출).

    URL 은 `/data_refresh` 그대로 둠 — frontend rename 만 (`refreshNews`)
    하고 backend path 는 호환성 위해 유지. 2분 cooldown — 외부 API 보호.
    """
    key = ticker.upper()
    ok_cd, remaining = await _try_acquire_cooldown(
        db, ticker, "data", _DATA_REFRESH_COOLDOWN_S
    )
    if not ok_cd:
        raise HTTPException(429, f"cooldown: try again in {remaining}s")

    # 사용자 피드백 (2026-05-14): "AI 의견은 뉴스공시가 새로고침되면 당연히
    # 변경되어야 한다" — Codex 시니어 리뷰 동의. ≥1건 으로 낮춤. 0건이면
    # sync 만 끝 (외부 API 변화 없는 시점에 LLM $0.25 낭비 방지). 전체
    # 새로고침 (`/full_refresh`) 은 threshold 무시 무조건 trigger.
    _NEWS_TRIGGER_THRESHOLD = 1

    # sync_news 전 시점에 last_card 기준 새 뉴스 수 hint — frontend 가 polling
    # 시작 전 "AI 의견도 같이 갱신될 가능성" 표시 가능. 정확한 값은 background
    # 안에서 sync 후 다시 count — 이건 ballpark hint.
    last_card_gen_pre = (
        await db.execute(
            select(Analysis.generated_at)
            .where(
                Analysis.stock_id == stock.id,
                Analysis.schema_version == "v2",
            )
            .order_by(Analysis.date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if last_card_gen_pre is None:
        ai_refresh_likely_pre = True  # 첫 분석 — 무조건 trigger
    else:
        unseen_count_pre = (
            await db.execute(
                select(func.count())
                .select_from(News)
                .where(
                    News.stock_id == stock.id,
                    News.published_at > last_card_gen_pre,
                )
            )
        ).scalar() or 0
        ai_refresh_likely_pre = unseen_count_pre >= _NEWS_TRIGGER_THRESHOLD

    async def _sync_news_and_maybe_analyze() -> None:
        from app.models import News as _News
        from app.models import Stock as _Stock
        from sqlalchemy import func as _f

        async with async_session() as own_db:
            fresh = (
                await own_db.execute(
                    select(_Stock).where(_Stock.ticker == ticker)
                )
            ).scalar_one_or_none()
            if not fresh:
                return

            last_card = (
                await own_db.execute(
                    select(Analysis.generated_at)
                    .where(
                        Analysis.stock_id == fresh.id,
                        Analysis.schema_version == "v2",
                    )
                    .order_by(Analysis.date.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            for fn in (sync_news, sync_disclosures):
                try:
                    await fn(own_db, fresh)
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "data_refresh %s collector %s failed: %s",
                        ticker, fn.__name__, e,
                    )

            if last_card is None:
                new_news_count = 999
            else:
                new_news_count = (
                    await own_db.execute(
                        select(_f.count())
                        .select_from(_News)
                        .where(
                            _News.stock_id == fresh.id,
                            _News.published_at > last_card,
                        )
                    )
                ).scalar() or 0

        if new_news_count >= _NEWS_TRIGGER_THRESHOLD:
            logger.info(
                "data_refresh %s: %d new articles since last card → "
                "auto-trigger analyze() for AI narrative refresh",
                ticker, new_news_count,
            )
            try:
                await analyze(ticker)
            except Exception as e:  # noqa: BLE001
                logger.warning("data_refresh auto-analyze failed %s: %s", ticker, e)
        else:
            logger.info(
                "data_refresh %s: only %d new articles (< %d threshold) — "
                "skipping LLM narrative (cost saved)",
                ticker, new_news_count, _NEWS_TRIGGER_THRESHOLD,
            )

    bg.add_task(_sync_news_and_maybe_analyze)
    return {
        "status": "data_refresh_queued",
        "ticker": key,
        "auto_analyze_threshold_news": _NEWS_TRIGGER_THRESHOLD,
        # frontend hint — sync 가 새 뉴스 0건 추가하면 actual analyze trigger
        # 안 됨. 그래도 sync 전 시점 count 가 ≥1 이거나 첫 분석이면 likely.
        "ai_refresh_likely": ai_refresh_likely_pre,
    }


@router.post("/{ticker}/full_refresh", status_code=202)
async def full_refresh(
    ticker: str,
    bg: BackgroundTasks,
    stock: Stock = Depends(get_stock_or_404),
    db: AsyncSession = Depends(get_db),
):
    """전체 새로고침 — 가격 + 뉴스 + 공시 동기화 후 무조건 AI 재생성.

    3 버튼 (가격 / 뉴스공시 / AI 의견) 따로 누르는 부담을 줄이려는 사용자
    요청 (2026-05-14). 이건 비싼 액션 — LLM $0.25 + 외부 API 3-4 콜.
    5분 cooldown 으로 `/refresh` 와 동일 비용 protection.

    배경:
      1. sync_prices / sync_news / sync_disclosures 병렬 (asyncio.gather)
      2. analyze() — 비용 발생 단계, threshold 없이 무조건.

    smart-trigger (`/data_refresh` 의 ≥1건 조건) 가드는 적용 안 함 — "전체
    새로고침" 클릭 자체가 사용자의 명시적 LLM 비용 동의로 해석.
    """
    if not can_proceed():
        raise HTTPException(503, "daily analysis budget exceeded")

    key = ticker.upper()
    ok_cd, remaining = await _try_acquire_cooldown(
        db, ticker, "full", settings.analysis_cooldown_seconds
    )
    if not ok_cd:
        raise HTTPException(429, f"cooldown: try again in {remaining}s")

    ok, reason = await _ensure_analyzable(ticker, stock, db)
    if not ok:
        raise HTTPException(422, f"not analyzable: {reason}")

    async def _sync_all_then_analyze() -> None:
        import asyncio as _asyncio

        async with async_session() as own_db:
            fresh = (
                await own_db.execute(
                    select(Stock).where(Stock.ticker == ticker)
                )
            ).scalar_one_or_none()
            if not fresh:
                return

            async def _safe(fn) -> None:
                try:
                    await fn(own_db, fresh)
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "full_refresh %s collector %s failed: %s",
                        ticker, fn.__name__, e,
                    )

            # 가족 dev — own_db 는 단일 세션이라 진짜 병렬 X (직렬 await).
            # sync_prices 1-2s + sync_news 2-3s + sync_disclosures 1-2s = ~5s.
            # 별 세션 split 으로 진짜 병렬도 가능하지만 commit 충돌 위험 ↑.
            # 5분 cooldown 안에서 5s 추가 sync 는 허용 가능한 trade-off.
            for fn in (sync_prices, sync_news, sync_disclosures):
                await _safe(fn)

        try:
            await analyze(ticker)
        except Exception as e:  # noqa: BLE001
            logger.warning("full_refresh analyze failed %s: %s", ticker, e)

    bg.add_task(_sync_all_then_analyze)
    bg.add_task(_extract_relations_safe, ticker)
    return {"status": "full_refresh_queued", "ticker": key}


@router.post("/{ticker}/refresh", status_code=202)
async def force_refresh(
    ticker: str,
    bg: BackgroundTasks,
    stock: Stock = Depends(get_stock_or_404),
    db: AsyncSession = Depends(get_db),
):
    if not can_proceed():
        raise HTTPException(503, "daily analysis budget exceeded")

    key = ticker.upper()
    ok_cd, remaining = await _try_acquire_cooldown(
        db, ticker, "refresh", settings.analysis_cooldown_seconds
    )
    if not ok_cd:
        raise HTTPException(429, f"cooldown: try again in {remaining}s")
    ok, reason = await _ensure_analyzable(ticker, stock, db)
    if not ok:
        raise HTTPException(422, f"not analyzable: {reason}")
    bg.add_task(analyze, ticker)
    bg.add_task(_extract_relations_safe, ticker)
    return {"status": "refresh_queued", "ticker": key}
