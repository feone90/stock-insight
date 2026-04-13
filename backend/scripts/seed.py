"""기존 mock 데이터를 PostgreSQL에 적재하는 seed 스크립트."""

import asyncio
from datetime import date

from sqlalchemy import select

from app.database import async_session, engine
from app.models import (
    Analysis,
    Base,
    DailyKeyword,
    Favorite,
    KeywordDetail,
    PriceHistory,
    Stock,
)
from app.mocks.stocks import STOCKS
from app.mocks.prices import generate_prices
from app.mocks.analysis import ANALYSES, STATS


async def seed():
    async with async_session() as session:
        # 1. Stocks
        stock_map: dict[str, int] = {}  # ticker → stock.id

        for s in STOCKS:
            existing = await session.execute(
                select(Stock).where(Stock.ticker == s["ticker"])
            )
            stock = existing.scalar_one_or_none()
            if stock:
                stock_map[s["ticker"]] = stock.id
                print(f"  Skip existing: {s['ticker']}")
                continue

            stock = Stock(
                ticker=s["ticker"],
                name=s["name"],
                market=s["market"],
                sector=s["sector"],
                current_price=s["current_price"],
                change=s["change"],
                change_percent=s["change_percent"],
            )
            session.add(stock)
            await session.flush()
            stock_map[s["ticker"]] = stock.id
            print(f"  Added stock: {s['ticker']} (id={stock.id})")

        # 2. Price History
        for ticker, stock_id in stock_map.items():
            existing_count_result = await session.execute(
                select(PriceHistory).where(PriceHistory.stock_id == stock_id).limit(1)
            )
            if existing_count_result.scalar_one_or_none():
                print(f"  Skip prices for {ticker} (already exist)")
                continue

            prices = generate_prices(ticker, days=90)
            for p in prices:
                session.add(PriceHistory(
                    stock_id=stock_id,
                    date=date.fromisoformat(p["date"]),
                    open=p["open"],
                    high=p["high"],
                    low=p["low"],
                    close=p["close"],
                    volume=p["volume"],
                ))
            print(f"  Added {len(prices)} price records for {ticker}")

        # 3. Analysis + Keywords + DailyKeywords
        for ticker, analysis_data in ANALYSES.items():
            stock_id = stock_map.get(ticker)
            if not stock_id:
                continue

            existing = await session.execute(
                select(Analysis).where(Analysis.stock_id == stock_id).limit(1)
            )
            if existing.scalar_one_or_none():
                print(f"  Skip analysis for {ticker} (already exists)")
                continue

            analysis = Analysis(
                stock_id=stock_id,
                date=date.fromisoformat(analysis_data["date"]),
                period_type=analysis_data["period_type"],
                summary=analysis_data["summary"],
                feedback=analysis_data["feedback"],
            )
            session.add(analysis)
            await session.flush()

            for kw in analysis_data["keywords"]:
                session.add(KeywordDetail(
                    analysis_id=analysis.id,
                    keyword=kw["keyword"],
                    type=kw["type"],
                    detail=kw["detail"],
                    source=kw["source"],
                    impact_level=kw["impact_level"],
                    duration=kw["duration"],
                ))

            for dk in analysis_data["daily_keywords"]:
                session.add(DailyKeyword(
                    analysis_id=analysis.id,
                    date=date.fromisoformat(dk["date"]),
                    keyword=dk["keyword"],
                    type=dk["type"],
                ))

            print(f"  Added analysis for {ticker}: {len(analysis_data['keywords'])} keywords, {len(analysis_data['daily_keywords'])} daily")

        # 4. Favorites (삼성전자, 테슬라 기본 즐겨찾기)
        for ticker in ["005930", "TSLA"]:
            stock_id = stock_map.get(ticker)
            if not stock_id:
                continue

            existing = await session.execute(
                select(Favorite).where(Favorite.stock_id == stock_id)
            )
            if existing.scalar_one_or_none():
                print(f"  Skip favorite for {ticker} (already exists)")
                continue

            session.add(Favorite(user_id="default", stock_id=stock_id))
            print(f"  Added favorite: {ticker}")

        await session.commit()
        print("\nSeed 완료!")


if __name__ == "__main__":
    asyncio.run(seed())
