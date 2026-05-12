from urllib.parse import unquote

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import decode_token
from app.database import get_db
from app.dependencies import get_stock_or_404
from app.models import Favorite, Stock
from app.schemas.stock import FavoriteActionResponse, StockResponse

router = APIRouter(prefix="/api/favorites", tags=["favorites"])

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


@router.post("/{ticker}", response_model=FavoriteActionResponse)
async def add(stock: Stock = Depends(get_stock_or_404), user_id: str = Depends(_get_user_id), db: AsyncSession = Depends(get_db)):
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
