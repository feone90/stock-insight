"""Data layer tests — `assemble_data_layer` aggregates 5 deterministic fetches.

Most cases mock the individual sub-fetches because the test fixture shares a
single AsyncSession across the gather (production opens fresh sessions per
fetch from the connection pool, so concurrent ops never collide there).
Direct-DB cases use a single sequential call.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.models import News, PriceHistory, Stock
from app.models.relation import StockRelation
from app.schemas.card import DataLayer
from app.services.analyst.data_layer import (
    _CitationPool,
    _build_news,
    _fetch_data_timestamps,
    _fetch_recent_news,
    _fetch_relations_data,
    assemble_data_layer,
    fetch_stock_identity,
)


@pytest_asyncio.fixture
async def db_for_data_layer(db, monkeypatch):
    """Share the test session for direct-DB helper tests (sequential calls)."""

    @asynccontextmanager
    async def _session():
        yield db

    monkeypatch.setattr("app.services.analyst.data_layer.async_session", _session)
    return db


def _full_indicators_response() -> dict:
    return {
        "rsi_14": 58.0, "atr_pct": 2.0, "ma_stack": "정배열",
        "rvol_20": 1.4, "obv_ratio": 1.0, "cmf_20": 0.05,
        "citations": [{"source_type": "db", "label": "DB · price_history"}],
    }


def _full_macro_response() -> dict:
    return {
        "vix": 18.7, "us_10y": 4.6,
        "fx_pairs": {"USD/KRW": 1378.0},
        "upcoming_events": [],
        "citations": [{"source_type": "market_data", "label": "DB · macro_factors"}],
    }


def _full_fundamentals_response() -> dict:
    return {
        "per": 12.0, "pbr": 1.1,
        "market_cap_krw": 1e12, "dividend_yield": 2.0,
        "label": "DB · financials (2026Q1)",
    }


def _full_news_response() -> dict:
    return {
        "items": [
            {
                "title": "HBM3E 양산", "source": "조선",
                "url": "https://example.com/n/1",
                "published_at": datetime.utcnow() - timedelta(days=1),
                "summary": "ok",
            }
        ]
    }


def _full_relations_response(is_stale: bool = False) -> dict:
    return {
        "relations": [
            {
                "target_ticker": "000660", "target_name": "SK하이닉스",
                "relation_type": "peer", "strength": 0.9, "today_change_pct": 2.8,
            }
        ],
        "is_stale": is_stale,
    }


def _patch_all_fetches(
    monkeypatch,
    *,
    indicators=None,
    macro=None,
    fundamentals=None,
    news=None,
    relations=None,
    classify=None,
    timestamps=None,
):
    monkeypatch.setattr(
        "app.services.analyst.data_layer.get_indicators",
        AsyncMock(return_value=indicators if indicators is not None else _full_indicators_response()),
    )
    monkeypatch.setattr(
        "app.services.analyst.data_layer.get_macro_context",
        AsyncMock(return_value=macro if macro is not None else _full_macro_response()),
    )
    monkeypatch.setattr(
        "app.services.analyst.data_layer._fetch_fundamentals",
        AsyncMock(return_value=fundamentals if fundamentals is not None else _full_fundamentals_response()),
    )
    monkeypatch.setattr(
        "app.services.analyst.data_layer._fetch_recent_news",
        AsyncMock(return_value=news if news is not None else _full_news_response()),
    )
    monkeypatch.setattr(
        "app.services.analyst.data_layer._fetch_relations_data",
        AsyncMock(return_value=relations if relations is not None else _full_relations_response()),
    )
    monkeypatch.setattr(
        "app.services.analyst.data_layer._fetch_data_timestamps",
        AsyncMock(
            return_value=timestamps
            if timestamps is not None
            else {"price_asof": None, "news_latest_at": None}
        ),
    )
    monkeypatch.setattr(
        "app.services.analyst.data_layer._fetch_recent_price_move_safe",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.analyst.data_layer.llm_classify_news",
        AsyncMock(return_value=classify if classify is not None else {"items": []}),
    )


@pytest.mark.asyncio
async def test_assemble_returns_full_data_layer(monkeypatch):
    _patch_all_fetches(monkeypatch)
    out = await assemble_data_layer("DL1")
    assert isinstance(out, DataLayer)
    assert out.technical is not None and out.technical.rsi_14 == 58.0
    assert out.macro is not None and out.macro.us_10y == 4.6
    assert out.fundamentals is not None and out.fundamentals.per == 12.0
    assert len(out.news) == 1
    assert out.news[0].impact == "neutral"
    assert len(out.relations_data) == 1
    assert out.relations_data[0].target_ticker == "000660"
    citation_ids = [c.id for c in out.data_citations]
    assert citation_ids == list(range(1, len(citation_ids) + 1))  # 1..K contiguous


@pytest.mark.asyncio
async def test_assemble_handles_missing_indicators_gracefully(monkeypatch):
    """< 30 days price history → indicators returns error → technical=None."""
    _patch_all_fetches(monkeypatch, indicators={"error": "insufficient data"})
    out = await assemble_data_layer("DL2")
    assert out.technical is None
    assert out.macro is not None  # other sections still populated
    assert out.fundamentals is not None


@pytest.mark.asyncio
async def test_assemble_handles_empty_news(monkeypatch):
    _patch_all_fetches(monkeypatch, news={"items": []})
    out = await assemble_data_layer("DL3")
    assert out.news == []


@pytest.mark.asyncio
async def test_assemble_handles_empty_macro(monkeypatch):
    _patch_all_fetches(monkeypatch, macro={"vix": None, "fx_pairs": {}, "citations": []})
    out = await assemble_data_layer("DL4")
    assert out.macro is None


@pytest.mark.asyncio
async def test_assemble_handles_indicator_exception(monkeypatch):
    """If a sub-fetch raises, the whole assemble must not raise."""
    async def boom(_ticker):
        raise RuntimeError("upstream blew up")

    _patch_all_fetches(monkeypatch)
    monkeypatch.setattr("app.services.analyst.data_layer.get_indicators", boom)
    out = await assemble_data_layer("DL5")
    assert out.technical is None  # graceful degrade
    assert out.macro is not None  # rest unaffected


@pytest.mark.asyncio
async def test_assemble_classifies_news_impact(monkeypatch):
    classify_response = {
        "items": [
            {"index": 0, "topic": "earnings", "sentiment": "positive", "impact": "positive"}
        ]
    }
    _patch_all_fetches(monkeypatch, classify=classify_response)
    out = await assemble_data_layer("DL6")
    assert out.news[0].impact == "positive"


@pytest.mark.asyncio
async def test_assemble_uses_asyncio_gather(monkeypatch):
    """All 5 fetches run concurrently."""
    delay = 0.05

    async def slow(*args, **kwargs):
        await asyncio.sleep(delay)
        return {}

    async def slow_indicators(_ticker):
        await asyncio.sleep(delay)
        return {"error": "no data"}

    async def slow_macro():
        await asyncio.sleep(delay)
        return {}

    monkeypatch.setattr("app.services.analyst.data_layer.get_indicators", slow_indicators)
    monkeypatch.setattr("app.services.analyst.data_layer.get_macro_context", slow_macro)
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_fundamentals", slow)
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_recent_news", slow)
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_relations_data", slow)
    # 2026-05-14 — 추가된 새 fetcher 6 개도 monkeypatch (concurrent 검증 fair).
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_political_signals", slow)
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_flow", slow)
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_insider", slow)
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_earnings", slow)
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_analyst_rating", slow)
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_price_target", slow)
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_data_timestamps", slow)
    monkeypatch.setattr("app.services.analyst.data_layer._fetch_recent_price_move_safe", slow)
    monkeypatch.setattr(
        "app.services.analyst.data_layer.llm_classify_news",
        AsyncMock(return_value={"items": []}),
    )

    start = asyncio.get_event_loop().time()
    await assemble_data_layer("DL7")
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed < delay * 3, f"expected gather (<~{delay*3}s), got {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_assemble_triggers_bg_refresh_when_relations_stale(monkeypatch):
    bg_called: list[str] = []

    async def fake_bg(ticker: str) -> None:
        bg_called.append(ticker)

    _patch_all_fetches(monkeypatch, relations=_full_relations_response(is_stale=True))
    monkeypatch.setattr("app.services.analyst.data_layer._bg_refresh_relations", fake_bg)

    await assemble_data_layer("DL8")
    # Yield to event loop so the fire-and-forget task runs
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert "DL8" in bg_called


@pytest.mark.asyncio
async def test_assemble_skips_bg_refresh_when_relations_fresh(monkeypatch):
    bg_called: list[str] = []

    async def fake_bg(ticker: str) -> None:
        bg_called.append(ticker)

    _patch_all_fetches(monkeypatch, relations=_full_relations_response(is_stale=False))
    monkeypatch.setattr("app.services.analyst.data_layer._bg_refresh_relations", fake_bg)

    await assemble_data_layer("DL9")
    await asyncio.sleep(0)
    assert bg_called == []


# ---------------------------------------------------------------------------
# Direct DB helpers — single sequential call, safe with shared session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_recent_news_filters_older_than_14_days(db_for_data_layer):
    db = db_for_data_layer
    s = Stock(ticker="NW1", name="NW Corp", market="KRX", sector="x", current_price=10)
    db.add(s)
    await db.flush()
    db.add_all([
        News(
            stock_id=s.id, title="NW Corp recent", source="src",
            url="https://e.com/recent",
            published_at=datetime.utcnow() - timedelta(days=2),
            content="NW Corp recent " * 12,
        ),
        News(
            stock_id=s.id, title="too old", source="src",
            url="https://e.com/old",
            published_at=datetime.utcnow() - timedelta(days=30),
            content="too old",
        ),
    ])
    await db.commit()

    res = await _fetch_recent_news("NW1")
    titles = [it["title"] for it in res["items"]]
    assert "NW Corp recent" in titles
    assert "too old" not in titles


@pytest.mark.asyncio
async def test_fetch_recent_news_prioritizes_stock_specific_items(db_for_data_layer):
    db = db_for_data_layer
    s = Stock(ticker="660TEST", name="SK하이닉스", market="KRX", sector="반도체", current_price=10)
    db.add(s)
    await db.flush()
    now = datetime.utcnow()
    db.add_all([
        News(
            stock_id=s.id,
            title="삼성 노사 오전 담판 재개",
            source="src",
            url="https://e.com/samsung-labor",
            published_at=now,
            content="삼성전자 노사 협상 기사 " * 20,
        ),
        News(
            stock_id=s.id,
            title="SK하이닉스, HBM 공급 확대 기대",
            source="src",
            url="https://e.com/sk-hbm",
            published_at=now - timedelta(minutes=5),
            content="SK하이닉스 HBM 수요가 늘고 있다는 기사 " * 20,
        ),
    ])
    await db.commit()

    res = await _fetch_recent_news("660TEST")
    titles = [it["title"] for it in res["items"]]

    assert titles[0] == "SK하이닉스, HBM 공급 확대 기대"
    assert "삼성 노사 오전 담판 재개" not in titles


@pytest.mark.asyncio
async def test_build_news_creates_summary_when_content_is_empty(monkeypatch):
    monkeypatch.setattr(
        "app.services.analyst.data_layer.llm_classify_news",
        AsyncMock(return_value={"items": [{"index": 0, "impact": "positive"}]}),
    )
    pool = _CitationPool()

    items = await _build_news(
        {
            "items": [
                {
                    "title": "SK하이닉스, HBM 공급 확대 기대",
                    "source": "src",
                    "url": "https://e.com/sk-hbm",
                    "published_at": datetime.utcnow(),
                    "summary": "",
                }
            ]
        },
        pool,
    )

    assert items[0].summary
    assert "본문을 아직 확보하지 못해" in items[0].summary
    assert "HBM 공급 확대 기대" not in items[0].summary


@pytest.mark.asyncio
async def test_build_news_surfaces_body_quote_and_importance(monkeypatch):
    monkeypatch.setattr(
        "app.services.analyst.data_layer.llm_classify_news",
        AsyncMock(return_value={"items": [{"index": 0, "impact": "positive"}]}),
    )
    monkeypatch.setattr(
        "app.services.analyst.data_layer._analyze_news_items",
        AsyncMock(return_value={
            0: {
                "summary": "경영평가 1위 배경이 AI 반도체 매출과 투자 확대였다고 짚었다.",
                "key_quote": "SK하이닉스는 800점 만점에 최고점인 648.3점을 받아 종합 1위에 올랐다.",
                "why_it_matters": "AI 메모리 수요가 실적 평가로 확인됐다는 점에서 프리미엄 유지 여부와 연결된다.",
            }
        }),
    )
    pool = _CitationPool()

    items = await _build_news(
        {
            "items": [
                {
                    "title": "SK하이닉스, 2년 연속 경영평가 1위",
                    "source": "src",
                    "url": "https://e.com/sk-score",
                    "published_at": datetime.utcnow(),
                    "summary": "SK하이닉스는 800점 만점에 최고점인 648.3점을 받아 종합 1위에 올랐다.",
                }
            ]
        },
        pool,
    )

    assert items[0].summary.startswith("경영평가 1위")
    assert items[0].key_quote == "SK하이닉스는 800점 만점에 최고점인 648.3점을 받아 종합 1위에 올랐다."
    assert items[0].why_it_matters.startswith("AI 메모리 수요")


@pytest.mark.asyncio
async def test_build_news_never_surfaces_english_summary_for_us_news(monkeypatch):
    monkeypatch.setattr(
        "app.services.analyst.data_layer.llm_classify_news",
        AsyncMock(return_value={"items": [{"index": 0, "impact": "positive"}]}),
    )
    monkeypatch.setattr(
        "app.services.analyst.data_layer._analyze_news_items",
        AsyncMock(return_value={}),
    )
    pool = _CitationPool()

    items = await _build_news(
        {
            "items": [
                {
                    "title": "Why Microsoft stock is trading up today",
                    "source": "Yahoo Finance",
                    "url": "https://finance.yahoo.com/msft",
                    "published_at": datetime.utcnow(),
                    "summary": (
                        "Microsoft shares rose after reports revealed stronger Azure demand. "
                        "Analysts said enterprise AI spending remained resilient across large customers."
                    ),
                }
            ]
        },
        pool,
    )

    assert "Microsoft shares rose" not in items[0].summary
    assert "영문 기사 본문" in items[0].summary
    assert items[0].key_quote is None


@pytest.mark.asyncio
async def test_build_news_rejects_non_korean_llm_output_for_us_news(monkeypatch):
    monkeypatch.setattr(
        "app.services.analyst.data_layer.llm_classify_news",
        AsyncMock(return_value={"items": [{"index": 0, "impact": "positive"}]}),
    )
    monkeypatch.setattr(
        "app.services.analyst.data_layer._analyze_news_items",
        AsyncMock(return_value={
            0: {
                "summary": "Microsoft shares rose after stronger Azure demand.",
                "key_quote": "Azure demand remained resilient.",
                "why_it_matters": "Cloud revenue is important for margins.",
            }
        }),
    )
    pool = _CitationPool()

    items = await _build_news(
        {
            "items": [
                {
                    "title": "Why Microsoft stock is trading up today",
                    "source": "Yahoo Finance",
                    "url": "https://finance.yahoo.com/msft",
                    "published_at": datetime.utcnow(),
                    "summary": (
                        "Microsoft shares rose after reports revealed stronger Azure demand. "
                        "Analysts said enterprise AI spending remained resilient across large customers."
                    ),
                }
            ]
        },
        pool,
    )

    assert "Microsoft shares rose" not in items[0].summary
    assert items[0].key_quote is None
    assert items[0].why_it_matters is None


@pytest.mark.asyncio
async def test_build_news_accepts_korean_analysis_for_us_news(monkeypatch):
    monkeypatch.setattr(
        "app.services.analyst.data_layer.llm_classify_news",
        AsyncMock(return_value={"items": [{"index": 0, "impact": "positive"}]}),
    )
    monkeypatch.setattr(
        "app.services.analyst.data_layer._analyze_news_items",
        AsyncMock(return_value={
            0: {
                "summary": "마이크로소프트 주가는 애저 수요와 투자자 매수 소식에 상승했다.",
                "key_quote": "애저 수요가 견조하다는 점이 주가 상승의 핵심 배경으로 제시됐다.",
                "why_it_matters": "클라우드 성장세는 마이크로소프트의 이익률과 AI 투자 회수 가능성을 좌우한다.",
            }
        }),
    )
    pool = _CitationPool()

    items = await _build_news(
        {
            "items": [
                {
                    "title": "Why Microsoft stock is trading up today",
                    "source": "Yahoo Finance",
                    "url": "https://finance.yahoo.com/msft",
                    "published_at": datetime.utcnow(),
                    "summary": (
                        "Microsoft shares rose after reports revealed stronger Azure demand. "
                        "Analysts said enterprise AI spending remained resilient across large customers."
                    ),
                }
            ]
        },
        pool,
    )

    assert items[0].summary.startswith("마이크로소프트")
    assert items[0].key_quote.startswith("애저 수요")
    assert items[0].why_it_matters.startswith("클라우드 성장세")


@pytest.mark.asyncio
async def test_fetch_recent_news_drops_caption_duplicates(db_for_data_layer):
    db = db_for_data_layer
    s = Stock(ticker="TSTCAP", name="삼성전자", market="KRX", sector="반도체", current_price=10)
    db.add(s)
    await db.flush()
    now = datetime.utcnow()
    db.add_all([
        News(
            stock_id=s.id,
            title="협상장 향하는 여명구 삼성전자 사측 대표교섭위원",
            source="뉴시스",
            url="https://e.com/photo1",
            published_at=now,
            content="",
        ),
        News(
            stock_id=s.id,
            title="회의장 향하는 여명구 삼성전자 사측 대표교섭위원",
            source="뉴시스",
            url="https://e.com/photo2",
            published_at=now - timedelta(minutes=1),
            content="",
        ),
        News(
            stock_id=s.id,
            title="삼성전자 노사, 임금협상 재개",
            source="src",
            url="https://e.com/labor",
            published_at=now - timedelta(minutes=2),
            content="삼성전자 노사가 임금협상을 재개했고 반도체 생산 차질 가능성을 낮추는 방향으로 논의를 이어갔다. " * 5,
        ),
    ])
    await db.commit()

    res = await _fetch_recent_news("TSTCAP")
    titles = [it["title"] for it in res["items"]]

    assert titles == ["삼성전자 노사, 임금협상 재개"]


@pytest.mark.asyncio
async def test_fetch_recent_news_drops_market_wrap_single_mention(db_for_data_layer):
    db = db_for_data_layer
    s = Stock(ticker="TSTKOLON", name="코오롱티슈진", market="KOSDAQ", sector="바이오", current_price=10)
    db.add(s)
    await db.flush()
    now = datetime.utcnow()
    market_wrap = (
        "코스피 지수가 외국인 투자자들의 투매 영향으로 하락 마감했다. "
        "코스닥 시가총액 상위 10개 종목 가운데 에코프로비엠, 에코프로, "
        "레인보우로보틱스, 코오롱티슈진(-1.66%), 삼천당제약 등이 내렸다. "
        "서울 외환시장에서 원화 환율은 상승했고 내일 증시는 미국 고용 지표 영향을 받을 전망이다."
    )
    db.add_all([
        News(
            stock_id=s.id,
            title="개인 6조 순매수도 '역부족'…3% 하락 코스피, 7270선 마감 [시황]",
            source="데일리안",
            url="https://n.news.naver.com/mnews/article/119/0003092157",
            published_at=now,
            content=market_wrap,
        ),
        News(
            stock_id=s.id,
            title="코오롱티슈진, 신약 임상 진행 현황 공개",
            source="src",
            url="https://e.com/kolon",
            published_at=now - timedelta(minutes=1),
            content="코오롱티슈진은 신약 임상 진행 현황을 공개했다. 코오롱티슈진은 환자 등록과 주요 평가변수 확인 일정을 제시했다. " * 3,
        ),
    ])
    await db.commit()

    res = await _fetch_recent_news("TSTKOLON")
    titles = [it["title"] for it in res["items"]]

    assert titles == ["코오롱티슈진, 신약 임상 진행 현황 공개"]


@pytest.mark.asyncio
async def test_fetch_relations_data_detects_stale(db_for_data_layer):
    db = db_for_data_layer
    s = Stock(ticker="RL1", name="x", market="KRX", sector="x", current_price=10)
    db.add(s)
    await db.flush()
    db.add(
        StockRelation(
            from_stock_id=s.id, to_target="000660", to_kind="stock",
            relation_type="peer", strength=0.8,
            refreshed_at=datetime.utcnow() - timedelta(days=10),
        )
    )
    await db.commit()
    res = await _fetch_relations_data("RL1")
    assert res["is_stale"] is True
    assert len(res["relations"]) == 1


@pytest.mark.asyncio
async def test_fetch_stock_identity_returns_db_fields(db_for_data_layer):
    db = db_for_data_layer
    s = Stock(
        ticker="ID1", name="아이덴티티", market="KRX", sector="반도체",
        current_price=88.5, change=1.2, change_percent=1.4,
    )
    db.add(s)
    await db.commit()
    out = await fetch_stock_identity("ID1")
    assert out["ticker"] == "ID1"
    assert out["name_ko"] == "아이덴티티"
    assert out["sector"] == "반도체"
    assert out["price"] == 88.5
    assert isinstance(out["asof"], datetime)


@pytest.mark.asyncio
async def test_fetch_data_timestamps_reads_latest_rows(db_for_data_layer):
    """price_asof = MAX(PriceHistory.date), news_latest_at = MAX(News.published_at).

    카드 헤더의 "가격: N분 전" / "최신 뉴스: HH:MM" 표시는 이 두 값으로
    결정된다. 새 가격/뉴스 sync 가 들어오면 즉시 카드에 반영되어야 함.
    """
    db = db_for_data_layer
    s = Stock(ticker="TS1", name="x", market="KRX", sector="x", current_price=10)
    db.add(s)
    await db.flush()

    latest_news_at = datetime.utcnow() - timedelta(hours=2)
    db.add_all([
        PriceHistory(stock_id=s.id, date=date.today(), open=1, high=1, low=1, close=1, volume=1),
        PriceHistory(stock_id=s.id, date=date.today() - timedelta(days=5), open=1, high=1, low=1, close=1, volume=1),
        News(stock_id=s.id, title="recent", source="src", url="https://e.com/recent", published_at=latest_news_at, content="x"),
        News(stock_id=s.id, title="older", source="src", url="https://e.com/older", published_at=datetime.utcnow() - timedelta(days=4), content="x"),
    ])
    await db.commit()

    res = await _fetch_data_timestamps("TS1")
    # PriceHistory.date 는 date — fetcher 가 UTC midnight 으로 promote.
    assert res["price_asof"] is not None
    assert res["price_asof"].date() == date.today()
    # 2026-05-15 — fetcher 가 모든 timestamp 에 UTC tzinfo 부착 (frontend
    # KST 환경 9시간 어긋남 fix). naive 와 aware 직접 비교 불가능 → tz strip
    # 후 비교.
    from datetime import timezone as _tz
    assert res["news_latest_at"] is not None
    assert res["news_latest_at"].tzinfo == _tz.utc
    assert res["news_latest_at"].replace(tzinfo=None) == latest_news_at


@pytest.mark.asyncio
async def test_fetch_data_timestamps_returns_none_for_empty_stock(db_for_data_layer):
    db = db_for_data_layer
    s = Stock(ticker="TS2", name="x", market="KRX", sector="x", current_price=10)
    db.add(s)
    await db.commit()
    res = await _fetch_data_timestamps("TS2")
    assert res == {"price_asof": None, "news_latest_at": None}


@pytest.mark.asyncio
async def test_assemble_propagates_timestamps_into_data_layer(monkeypatch):
    """DataLayer.price_asof / news_latest_at 가 채워져야 카드 헤더에 노출됨."""
    now = datetime.utcnow()
    _patch_all_fetches(
        monkeypatch,
        timestamps={"price_asof": now, "news_latest_at": now - timedelta(minutes=30)},
    )
    out = await assemble_data_layer("DL_TS")
    assert out.price_asof == now
    assert out.news_latest_at == now - timedelta(minutes=30)


def test_citation_pool_assigns_sequential_ids():
    p = _CitationPool()
    a = p.add("db", "alpha")
    b = p.add("news", "beta", url="https://example.com")
    c = p.add("web", "gamma")
    assert (a, b, c) == (1, 2, 3)
    assert [item.id for item in p.items] == [1, 2, 3]
    assert p.items[1].url == "https://example.com"
