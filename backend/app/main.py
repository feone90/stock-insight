import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.auth import router as auth_router
from app.api.stocks import router as stocks_router
from app.api.analysis import router as analysis_router
from app.api.favorites import router as favorites_router
from app.api.admin import router as admin_router
from app.api.exchange_rates import router as exchange_rates_router
from app.api.cards import router as cards_router
from app.api.chat import router as chat_router
from app.api.ontology import router as ontology_router
from app.database import engine
from app.scheduler import init_scheduler, scheduler

logger = logging.getLogger(__name__)


async def _run_prewarm() -> None:
    """Background prewarm task spawned at app startup. Failures are swallowed —
    on-demand fetch will populate the cache lazily if prewarm is unavailable."""
    from app.services.external_data_adapters.loaders import top_favorited_tickers
    from app.services.external_data_adapters.prewarm import prewarm_favorites
    try:
        report = await prewarm_favorites(top_favorited_tickers)
        logger.info("prewarm complete: %s", report)
    except Exception as e:  # noqa: BLE001
        logger.warning("prewarm task failed: %s", e)


async def _run_startup_purge() -> None:
    """Deploy 마다 1회 환상 row 청소 (2026-05-14 SK하이닉스→동화약품 사례).

    옛 validator 가드 이전에 박힌 row 가 prod 에 남아있어 카드/그래프에
    계속 노출됨. 사용자가 admin endpoint 수동 호출하지 않게 startup 시
    자동 cleanup. 비용 0 — single SELECT + bulk DELETE, 보통 < 1s.
    """
    from app.database import async_session
    from app.services.ontology.purge import purge_llm_hallucinations

    try:
        async with async_session() as db:
            n = await purge_llm_hallucinations(db)
        if n > 0:
            logger.info("startup purge: removed %d hallucination relations", n)
    except Exception as e:  # noqa: BLE001
        logger.warning("startup purge failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_scheduler()

    # P1.5 Phase D: prewarm top favorites in background so the first card
    # load for popular tickers hits the warm cache (sub-second) instead of
    # cold (~5s KR / ~21s US).
    asyncio.create_task(_run_prewarm())

    # 2026-05-14: 환상 관계 일괄 청소 (사용자 피드백 — "옛 row를 db에서
    # 날리던가 정리를 하면되잖나"). deploy 마다 자동 실행.
    asyncio.create_task(_run_startup_purge())

    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)
    await engine.dispose()


app = FastAPI(title="StockInsight API", version="0.4.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(stocks_router)
app.include_router(analysis_router)
app.include_router(favorites_router)
app.include_router(admin_router)
app.include_router(exchange_rates_router)
app.include_router(chat_router)
app.include_router(cards_router)
app.include_router(ontology_router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
