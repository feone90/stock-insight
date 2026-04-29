"""top_favorited_tickers loader — orders by favorite count desc."""
from contextlib import asynccontextmanager

import pytest

from app.models import Favorite, Stock
from app.services.external_data_adapters import loaders


@pytest.mark.asyncio
async def test_top_favorited_tickers_orders_by_count_desc(db, monkeypatch):
    a = Stock(ticker="999991", name="A", market="KR", sector="IT")
    b = Stock(ticker="999992", name="B", market="KR", sector="IT")
    c = Stock(ticker="999993", name="C", market="KR", sector="IT")
    db.add_all([a, b, c])
    await db.flush()
    db.add_all([
        Favorite(user_id="u1", stock_id=a.id),
        Favorite(user_id="u2", stock_id=a.id),
        Favorite(user_id="u1", stock_id=b.id),
        # c has zero favorites — excluded by inner join
    ])
    await db.flush()

    @asynccontextmanager
    async def _session():
        yield db

    monkeypatch.setattr(loaders, "async_session", _session)

    result = await loaders.top_favorited_tickers(limit=20)
    assert "999991" in result
    assert "999992" in result
    assert "999993" not in result
    # Two favs > one fav → 999991 must come before 999992
    assert result.index("999991") < result.index("999992")
