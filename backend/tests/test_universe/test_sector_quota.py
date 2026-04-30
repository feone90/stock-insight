"""apply_sector_quota — pure algorithm cases."""
from __future__ import annotations

from app.services.universe.sector_quota import apply_sector_quota
from app.services.universe.types import UniverseRow


def _rows(specs: list[tuple[str, str, float | None]]) -> tuple[list[UniverseRow], dict[str, float | None]]:
    rows: list[UniverseRow] = []
    cap_by_ticker: dict[str, float | None] = {}
    for ticker, sector, cap in specs:
        rows.append(
            UniverseRow(
                ticker=ticker,
                name=ticker,
                market="KOSPI",
                sector=sector,
                industry_group=None,
                listing_date=None,
                universe_source="test",
            )
        )
        cap_by_ticker[ticker] = cap
    return rows, cap_by_ticker


def test_no_pool_topup_when_quota_met() -> None:
    candidates, _ = _rows([("A", "Tech", None), ("B", "Tech", None), ("C", "Tech", None)])
    pool = list(candidates)

    result = apply_sector_quota(candidates, pool, min_per_sector=2)

    assert [r.ticker for r in result] == ["A", "B", "C"]


def test_topup_pulls_from_pool_when_deficit() -> None:
    candidates, _ = _rows([("A", "Tech", None), ("B", "Health", None)])
    pool, _ = _rows(
        [
            ("A", "Tech", None),
            ("B", "Health", None),
            ("C", "Tech", None),
            ("D", "Health", None),
            ("E", "Health", None),
        ]
    )

    result = apply_sector_quota(candidates, pool, min_per_sector=2)
    tickers = {r.ticker for r in result}

    assert "A" in tickers and "B" in tickers
    assert "C" in tickers  # Tech topped up
    # Health needs 1 more (B exists, deficit=1)
    assert sum(1 for r in result if r.sector == "Health") == 2


def test_rank_key_promotes_largest_first() -> None:
    candidates, _ = _rows([("A", "Tech", None)])
    pool_rows, caps = _rows(
        [
            ("A", "Tech", 100.0),
            ("B", "Tech", 50.0),
            ("C", "Tech", 200.0),
            ("D", "Tech", 75.0),
        ]
    )

    result = apply_sector_quota(
        candidates,
        pool_rows,
        min_per_sector=3,
        rank_key=lambda r: caps.get(r.ticker),
    )
    added = [r.ticker for r in result if r.ticker != "A"]

    # Need 2 more (deficit = 3 - 1 = 2). C (200) and D (75) win over B (50).
    assert added == ["C", "D"]


def test_rank_key_none_ranks_last() -> None:
    candidates: list[UniverseRow] = []
    pool_rows, caps = _rows(
        [
            ("A", "Tech", None),
            ("B", "Tech", 100.0),
            ("C", "Tech", 50.0),
        ]
    )

    result = apply_sector_quota(
        candidates,
        pool_rows,
        min_per_sector=2,
        rank_key=lambda r: caps.get(r.ticker),
    )
    tickers = [r.ticker for r in result]

    # Ranked: B (100) > C (50) > A (None). Take top 2.
    assert tickers == ["B", "C"]
