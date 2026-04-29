"""Prewarm — graceful failure + correct fan-out (3 cases)."""
import pytest


class _FakeAdapter:
    def __init__(self):
        self.identity_calls = 0
        self.series_calls = 0

    async def fetch_identity(self, ticker):
        self.identity_calls += 1

    async def fetch_financial_series(self, ticker):
        self.series_calls += 1


@pytest.mark.asyncio
async def test_prewarm_favorites_fans_out_per_ticker(monkeypatch):
    from app.services.external_data_adapters import prewarm

    adapters: dict[str, _FakeAdapter] = {}

    def fake_get_adapter(ticker):
        return adapters.setdefault(ticker, _FakeAdapter())

    monkeypatch.setattr(prewarm, "get_adapter_for", fake_get_adapter)

    async def loader(limit):
        return ["005930", "TSLA", "AAPL"][:limit]

    result = await prewarm.prewarm_favorites(loader, limit=3)
    assert result == {"warmed": 3, "failed": 0}
    assert all(a.identity_calls == 1 and a.series_calls == 1 for a in adapters.values())


@pytest.mark.asyncio
async def test_prewarm_swallows_per_ticker_exception(monkeypatch):
    from app.services.external_data_adapters import prewarm

    class _FailingAdapter:
        async def fetch_identity(self, ticker):
            raise RuntimeError("boom")

        async def fetch_financial_series(self, ticker):  # not reached
            pass

    monkeypatch.setattr(prewarm, "get_adapter_for", lambda t: _FailingAdapter())

    async def loader(limit):
        return ["BAD"]

    result = await prewarm.prewarm_favorites(loader, limit=1)
    assert result == {"warmed": 0, "failed": 1}


@pytest.mark.asyncio
async def test_prewarm_handles_loader_failure_silently():
    from app.services.external_data_adapters import prewarm

    async def bad_loader(limit):
        raise RuntimeError("DB down")

    result = await prewarm.prewarm_favorites(bad_loader, limit=5)
    assert result == {"warmed": 0, "failed": 0}
