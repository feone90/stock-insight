from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.stocks import router as stocks_router
from app.api.analysis import router as analysis_router
from app.api.favorites import router as favorites_router
from app.api.admin import router as admin_router
from app.api.exchange_rates import router as exchange_rates_router
from app.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="StockInsight API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stocks_router)
app.include_router(analysis_router)
app.include_router(favorites_router)
app.include_router(admin_router)
app.include_router(exchange_rates_router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
