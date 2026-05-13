import asyncio
import logging
from urllib.parse import unquote

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import decode_token
from app.database import get_db
from app.dependencies import get_stock_or_404
from app.models import Favorite, Stock
from app.schemas.stock import FavoriteActionResponse, StockResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/favorites", tags=["favorites"])

# Codex review [medium]: in-process dedup of concurrent auto-analyze tasks for
# the same ticker. Two family members favoriting the same stock at once used
# to fire two LLM passes; now only the first runs and the second skips.
# For multi-worker scale, the atomic upsert in engine._persist (ON CONFLICT
# DO UPDATE on uq_analysis_stock_date_period) handles cross-process races —
# last writer wins instead of one task failing on the unique constraint.
_auto_analyze_locks: dict[int, asyncio.Lock] = {}


def _get_auto_analyze_lock(stock_id: int) -> asyncio.Lock:
    lock = _auto_analyze_locks.get(stock_id)
    if lock is None:
        lock = asyncio.Lock()
        _auto_analyze_locks[stock_id] = lock
    return lock

_optional_bearer = HTTPBearer(auto_error=False)
DEFAULT_USER = "default"


async def _get_user_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> str:
    """우선순위: X-User-Id header (가족 별 user) > JWT > 'default'.

    가족 dev에서는 로그인 없이 frontend localStorage 기반 user switcher가
    'X-User-Id: <name>'을 자동 첨부 → 사용자별 즐겨찾기 분리.
    """
    header_user = request.headers.get("X-User-Id")
    if header_user and header_user.strip():
        # frontend가 encodeURIComponent로 ASCII 변환 → 여기서 복원.
        return unquote(header_user.strip())[:64]
    if not credentials:
        return DEFAULT_USER
    try:
        payload = decode_token(credentials.credentials)
        return payload.get("sub", DEFAULT_USER)
    except JWTError:
        return DEFAULT_USER


@router.get("/users", response_model=list[str])
async def list_known_users(db: AsyncSession = Depends(get_db)):
    """즐겨찾기 1건이라도 추가한 user_id 전체 리스트.

    가족 dev: localStorage user는 device별이라 sync 안 됨. backend가 알고 있는
    user list를 frontend가 fetch → 본인 localStorage list와 merge → 모든 device
    에 가족 user list 자동 노출.
    """
    from sqlalchemy import distinct

    rows = (
        await db.execute(select(distinct(Favorite.user_id)).order_by(Favorite.user_id))
    ).scalars().all()
    return [u for u in rows if u and u != DEFAULT_USER]


@router.get("", response_model=list[StockResponse])
async def list_favorites(user_id: str = Depends(_get_user_id), db: AsyncSession = Depends(get_db)):
    # 로그인 사용자의 즐겨찾기가 비어있으면 default 즐겨찾기를 복사
    if user_id != DEFAULT_USER:
        count_result = await db.execute(
            select(Favorite).where(Favorite.user_id == user_id).limit(1)
        )
        if not count_result.scalar_one_or_none():
            default_favs = await db.execute(
                select(Favorite).where(Favorite.user_id == DEFAULT_USER)
            )
            for fav in default_favs.scalars().all():
                db.add(Favorite(user_id=user_id, stock_id=fav.stock_id))
            await db.commit()

    result = await db.execute(
        select(Stock)
        .join(Favorite, Favorite.stock_id == Stock.id)
        .where(Favorite.user_id == user_id)
        .order_by(Favorite.created_at.desc())
    )
    stocks = result.scalars().all()
    return [
        StockResponse(
            ticker=s.ticker, name=s.name, market=s.market, sector=s.sector,
            current_price=s.current_price, change=s.change, change_percent=s.change_percent,
        )
        for s in stocks
    ]


async def _auto_analyze_after_favorite(ticker: str, stock_id: int) -> None:
    """즐겨찾기 추가 직후 background self-heal — v2 카드 없으면 sync + analyze +
    relation extract 를 한 번에 처리.

    idempotent: 이미 v2 Analysis row 가 있으면 즉시 return. collectors 모두
    중복 호출 안전. budget 초과 시 LLM 호출만 skip.

    cards.py 의 `_ensure_analyzable` + `_extract_relations_safe` 가 카드 view
    경로에서 같은 일을 하지만 사용자가 카드 페이지로 가야 발동된다 — 즐겨찾기
    추가 시점에 미리 데이터 채워두면 첫 카드 view 가 instant.
    """
    from datetime import date, timedelta

    from app.collectors.disclosure import sync_disclosures
    from app.collectors.financials import sync_financials
    from app.collectors.news import sync_news
    from app.collectors.stock_price import sync_prices
    from app.database import async_session
    from app.models.analysis import Analysis
    from app.services.analyst.cost import can_proceed
    from app.services.analyst.engine import analyze
    from app.services.ontology import extract_news_relations_for_ticker

    lock = _get_auto_analyze_lock(stock_id)
    if lock.locked():
        logger.info(
            "auto-analyze[%s] skipped — another auto-analyze task already running for stock_id=%s",
            ticker, stock_id,
        )
        return

    async with lock:
        async with async_session() as db:
            # Re-check inside the lock — another task may have just finished
            # while we were waiting (or another worker on a multi-process
            # deployment may have written the row).
            existing = (
                await db.execute(
                    select(Analysis)
                    .where(
                        Analysis.stock_id == stock_id,
                        Analysis.schema_version == "v2",
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if existing and existing.card_data:
                logger.info("auto-analyze[%s] skipped — v2 card exists", ticker)
                return
            stock = (
                await db.execute(select(Stock).where(Stock.id == stock_id))
            ).scalar_one_or_none()
            if stock is None:
                return
            try:
                await sync_prices(db, stock)
                await sync_news(db, stock)
                await sync_financials(db, stock)
                await sync_disclosures(db, stock)
            except Exception as e:  # noqa: BLE001
                logger.warning("auto-analyze[%s] sync phase failed: %s", ticker, e)

        if not can_proceed():
            logger.info("auto-analyze[%s] LLM phase skipped — budget exceeded", ticker)
            return
        try:
            await analyze(ticker)
        except Exception as e:  # noqa: BLE001
            logger.warning("auto-analyze[%s] analyze failed: %s", ticker, e)
            return
        try:
            summary = await extract_news_relations_for_ticker(
                ticker,
                since=date.today() - timedelta(days=14),
                articles_per_run=10,
            )
            logger.info(
                "auto-analyze[%s] extract: seen=%s llm=%s upserted=%s",
                ticker,
                summary.get("articles_seen"),
                summary.get("llm_relations_returned"),
                summary.get("upserted"),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("auto-analyze[%s] extract failed: %s", ticker, e)


@router.post("/{ticker}", response_model=FavoriteActionResponse)
async def add(
    bg: BackgroundTasks,
    stock: Stock = Depends(get_stock_or_404),
    user_id: str = Depends(_get_user_id),
    db: AsyncSession = Depends(get_db),
):
    import asyncio

    from app.services.universe import promote_to_tier_2

    existing = await db.execute(
        select(Favorite).where(Favorite.user_id == user_id, Favorite.stock_id == stock.id)
    )
    if existing.scalar_one_or_none():
        return FavoriteActionResponse(status="already_exists", ticker=stock.ticker)

    db.add(Favorite(user_id=user_id, stock_id=stock.id))
    await db.commit()
    # P1.7 Phase B: 즐겨찾기 추가는 강한 user signal — tier 3 → 2 자동 승격.
    asyncio.create_task(promote_to_tier_2(stock.id))
    # 카드 첫 view 마찰 제거 — sync + analyze + extract 를 background 로 미리.
    bg.add_task(_auto_analyze_after_favorite, stock.ticker, stock.id)
    return FavoriteActionResponse(status="added", ticker=stock.ticker)


@router.delete("/{ticker}", response_model=FavoriteActionResponse)
async def remove(stock: Stock = Depends(get_stock_or_404), user_id: str = Depends(_get_user_id), db: AsyncSession = Depends(get_db)):
    fav_result = await db.execute(
        select(Favorite).where(Favorite.user_id == user_id, Favorite.stock_id == stock.id)
    )
    fav = fav_result.scalar_one_or_none()
    if fav:
        await db.delete(fav)
        await db.commit()

    return FavoriteActionResponse(status="removed", ticker=stock.ticker)
