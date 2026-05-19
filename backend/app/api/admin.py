from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserInfo, require_admin
from app.config import settings
from app.database import get_db
from app.dependencies import get_stock_or_404
from app.models import Favorite, Stock
from app.schemas.stock import SyncAllResult, SyncGlobalResult, SyncResult
from app.collectors.stock_price import sync_prices
from app.collectors.financials import sync_financials
from app.collectors.news import sync_news
from app.collectors.disclosure import sync_disclosures
from app.collectors.exchange_rate import sync_exchange_rates
from app.services.llm.adapter import get_adapter
from app.services.llm.analyzer import analyze_stock

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/sync/stock/{ticker}", response_model=SyncResult)
async def sync_stock(stock: Stock = Depends(get_stock_or_404), db: AsyncSession = Depends(get_db), _admin: UserInfo = Depends(require_admin)):

    prices_result = await sync_prices(db, stock)
    financials_result = await sync_financials(db, stock)
    news_result = await sync_news(db, stock)
    disclosures_result = await sync_disclosures(db, stock)

    # LLM 분석 (API 키가 설정된 경우만)
    analysis_result = {"analysis_created": False}
    if settings.llm_api_key:
        adapter = get_adapter()
        analysis_result = await analyze_stock(db, stock, adapter)

    errors = []
    for r in [prices_result, financials_result, news_result, disclosures_result, analysis_result]:
        if "error" in r:
            errors.append(r["error"])

    return {
        "status": "ok",
        "ticker": stock.ticker,
        "synced": {
            "prices": prices_result.get("prices_synced", 0),
            "financials": financials_result.get("financials_synced", 0),
            "news": news_result.get("news_synced", 0),
            "disclosures": disclosures_result.get("disclosures_synced", 0),
            "analysis": analysis_result.get("analysis_created", False),
        },
        "financials_detail": {
            k: financials_result.get(k)
            for k in ("source", "period", "per", "pbr", "roe", "market_cap", "revenue", "net_income")
        },
        "errors": errors,
    }


@router.post("/sync/global", response_model=SyncGlobalResult)
async def sync_global(db: AsyncSession = Depends(get_db), _admin: UserInfo = Depends(require_admin)):
    rates_result = await sync_exchange_rates(db)

    errors = []
    if "error" in rates_result:
        errors.append(rates_result["error"])

    return {
        "status": "ok",
        "synced": {
            "exchange_rates": rates_result.get("exchange_rates_synced", 0),
        },
        "errors": errors,
    }


@router.post("/sync/all", response_model=SyncAllResult)
async def sync_all(db: AsyncSession = Depends(get_db), _admin: UserInfo = Depends(require_admin)):
    # 모든 사용자의 즐겨찾기 종목 합집합 (중복 제거)
    fav_result = await db.execute(
        select(Stock).join(Favorite, Favorite.stock_id == Stock.id).distinct()
    )
    stocks = fav_result.scalars().all()

    total = {"prices": 0, "financials": 0, "news": 0, "disclosures": 0, "exchange_rates": 0, "analyses": 0}
    errors = []
    tickers_synced = []

    # LLM 어댑터 (키 설정 시 한 번만 생성)
    adapter = get_adapter() if settings.llm_api_key else None

    for stock in stocks:
        tickers_synced.append(stock.ticker)

        prices_result = await sync_prices(db, stock)
        financials_result = await sync_financials(db, stock)
        news_result = await sync_news(db, stock)
        disclosures_result = await sync_disclosures(db, stock)

        # LLM 분석
        analysis_result = {"analysis_created": False}
        if adapter:
            analysis_result = await analyze_stock(db, stock, adapter)

        total["prices"] += prices_result.get("prices_synced", 0)
        total["financials"] += financials_result.get("financials_synced", 0)
        total["news"] += news_result.get("news_synced", 0)
        total["disclosures"] += disclosures_result.get("disclosures_synced", 0)
        if analysis_result.get("analysis_created"):
            total["analyses"] += 1

        for r in [prices_result, financials_result, news_result, disclosures_result, analysis_result]:
            if "error" in r:
                errors.append(f"[{stock.ticker}] {r['error']}")

    rates_result = await sync_exchange_rates(db)
    total["exchange_rates"] = rates_result.get("exchange_rates_synced", 0)
    if "error" in rates_result:
        errors.append(rates_result["error"])

    return {
        "status": "ok",
        "stocks_synced": tickers_synced,
        "global_synced": True,
        "total_synced": total,
        "errors": errors,
    }


@router.post("/jobs/run/{job_id}")
async def run_job(job_id: str, _admin: UserInfo = Depends(require_admin)):
    """스케줄러의 cron 잡을 수동으로 즉시 실행. 첫 deploy 직후 cron 한 번도
    안 돈 상태에서 데이터 채우기 용도. 잡은 idempotent — 반복 호출 안전.

    Available job_id:
      - fred                : FRED 매크로 (VIX/US10Y/FedFunds/실업률) snapshot
      - sector_match        : universe-wide KSIC→GICS sector_match
      - news_extraction     : 뉴스 LLM RAG competitor/inverse 추출
      - sec_8k              : SEC 8-K Item 1.01 contract 추출
      - sec_10k_risk        : SEC 10-K Item 1A Risk Factors LLM RAG (Codex G)
      - dart_contract       : DART 단일판매·공급계약 LLM RAG (Codex F, KR 8-K)
      - regulatory_coshock  : political_signal_tickers → regulatory_link (Codex H)
      - ontology_refresh_all: 위 ontology 추출 5종 (news + sec_8k + 10k + dart + coshock)
                              + sector_match 한 번에 실행. 사용자가 카드에 새 관계를
                              제대로 노출시키고 싶을 때 최초 backfill / 주기 refresh 용
      - inverse_verify      : inverse signal 가격 상관관계 검증
      - universe_refresh    : reference universe (KOSPI + S&P 500) refresh
      - sync_favorites      : 즐겨찾기 종목 가격/재무/뉴스/공시 동기화
    """
    from app.scheduler import (
        run_fred_macro_sync,
        run_inverse_verification,
        run_news_extraction,
        run_sec_8k_extraction,
        scheduled_sync_job,
    )
    from app.services.ontology import (
        extract_10k_risk_for_universe,
        extract_dart_contracts_for_universe,
        extract_regulatory_coshock,
        universe_wide_sector_match,
    )
    from app.services.universe import nightly_universe_refresh

    from app.collectors.truth_social import sync_truth_social
    from app.database import async_session as _async_session
    from app.services.political.analyzer import analyze_pending_signals

    async def _truth_social_job():
        async with _async_session() as db:
            return await sync_truth_social(db)

    async def _political_analyze_job():
        async with _async_session() as db:
            return await analyze_pending_signals(db)

    async def _ontology_refresh_all():
        """F/G/H + 기존 news/sec_8k + sector_match 한 번에. 첫 backfill 또는
        주기 refresh 용. 시간 오래 걸림 (universe 전체, LLM 다회 호출). 결과는
        summary dict."""
        out: dict = {}
        try:
            out["sector_match"] = await universe_wide_sector_match()
        except Exception as e:  # noqa: BLE001
            out["sector_match"] = {"error": str(e)}
        try:
            out["news_extraction"] = await run_news_extraction()
        except Exception as e:  # noqa: BLE001
            out["news_extraction"] = {"error": str(e)}
        try:
            out["sec_8k"] = await run_sec_8k_extraction()
        except Exception as e:  # noqa: BLE001
            out["sec_8k"] = {"error": str(e)}
        try:
            out["sec_10k_risk"] = await extract_10k_risk_for_universe()
        except Exception as e:  # noqa: BLE001
            out["sec_10k_risk"] = {"error": str(e)}
        try:
            out["dart_contract"] = await extract_dart_contracts_for_universe()
        except Exception as e:  # noqa: BLE001
            out["dart_contract"] = {"error": str(e)}
        try:
            out["regulatory_coshock"] = await extract_regulatory_coshock()
        except Exception as e:  # noqa: BLE001
            out["regulatory_coshock"] = {"error": str(e)}
        return out

    jobs = {
        "fred": run_fred_macro_sync,
        "sector_match": universe_wide_sector_match,
        "news_extraction": run_news_extraction,
        "sec_8k": run_sec_8k_extraction,
        "sec_10k_risk": extract_10k_risk_for_universe,
        "dart_contract": extract_dart_contracts_for_universe,
        "regulatory_coshock": extract_regulatory_coshock,
        "ontology_refresh_all": _ontology_refresh_all,
        "inverse_verify": run_inverse_verification,
        "universe_refresh": nightly_universe_refresh,
        "sync_favorites": scheduled_sync_job,
        "truth_social": _truth_social_job,
        "political_analyze": _political_analyze_job,
    }
    if job_id not in jobs:
        raise HTTPException(
            status_code=404,
            detail=f"unknown job_id '{job_id}'. Available: {sorted(jobs.keys())}",
        )
    try:
        result = await jobs[job_id]()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"job '{job_id}' failed: {e}")
    # job 함수가 dict 반환 시 그대로 노출 (None인 경우 빈 dict). 검증/디버깅용.
    return {"status": "ok", "job": job_id, "result": result if result is not None else {}}


@router.post("/extract_relations/{ticker}")
async def extract_relations_for_one(
    ticker: str, _admin: UserInfo = Depends(require_admin)
):
    """한 ticker에 대해 LLM news relation extraction 강제 실행 + 결과 dict 반환.

    universe-wide news_extraction 잡이 빈 result 만 보여줘서 진단이 어렵기 때문에
    per-ticker 진입점을 따로 둔다. articles_seen/upserted/buffered + (있다면)
    LLM 이 만든 first relation 예시를 노출.
    """
    from datetime import date, timedelta
    from app.services.ontology import extract_news_relations_for_ticker

    try:
        summary = await extract_news_relations_for_ticker(
            ticker, since=date.today() - timedelta(days=14), articles_per_run=10
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, detail=f"extract failed: {e}")
    return {"status": "ok", "ticker": ticker, "summary": summary}


@router.get("/inspect/relations/{ticker}")
async def inspect_relations(
    ticker: str,
    db: AsyncSession = Depends(get_db),
    _admin: UserInfo = Depends(require_admin),
):
    """ticker의 outgoing StockRelation row 5건의 raw extra_metadata 노출.

    rationale 데이터 흐름 진단용 — LLM extract → validator → DB → data_layer.
    """
    from app.models.relation import StockRelation

    stock = (
        await db.execute(select(Stock).where(Stock.ticker == ticker.upper()))
    ).scalar_one_or_none()
    if not stock:
        raise HTTPException(404, detail=f"ticker '{ticker}' not in DB")
    rows = (
        await db.execute(
            select(StockRelation)
            .where(StockRelation.from_stock_id == stock.id)
            .order_by(StockRelation.refreshed_at.desc().nulls_last())
            .limit(10)
        )
    ).scalars().all()
    return {
        "ticker": ticker.upper(),
        "stock_id": stock.id,
        "rows": [
            {
                "to_target": r.to_target,
                "relation_type": r.relation_type,
                "source": r.source,
                "confidence": r.confidence,
                "refreshed_at": r.refreshed_at.isoformat() if r.refreshed_at else None,
                "extra_metadata": r.extra_metadata,
            }
            for r in rows
        ],
    }


@router.get("/inspect/news/{ticker}")
async def inspect_news(
    ticker: str,
    db: AsyncSession = Depends(get_db),
    _admin: UserInfo = Depends(require_admin),
):
    """ticker의 최근 뉴스 본문 길이 분포 + 샘플 5건. 본문 scraping 확인용."""
    from sqlalchemy import func
    from app.models.news import News

    stock = (
        await db.execute(select(Stock).where(Stock.ticker == ticker.upper()))
    ).scalar_one_or_none()
    if not stock:
        raise HTTPException(404, detail=f"ticker '{ticker}' not in DB")
    total = (
        await db.execute(
            select(func.count()).select_from(News).where(News.stock_id == stock.id)
        )
    ).scalar() or 0
    long_count = (
        await db.execute(
            select(func.count()).select_from(News).where(
                News.stock_id == stock.id,
                func.length(News.content) >= 200,
            )
        )
    ).scalar() or 0
    samples = (
        await db.execute(
            select(News.title, News.source, News.url, func.length(News.content).label("len"))
            .where(News.stock_id == stock.id)
            .order_by(News.published_at.desc())
            .limit(5)
        )
    ).all()
    return {
        "ticker": ticker.upper(),
        "stock_id": stock.id,
        "total_news": total,
        "with_long_body": long_count,
        "samples": [
            {"title": s.title, "source": s.source, "url": s.url, "content_len": s.len}
            for s in samples
        ],
    }


@router.post("/ontology/purge_noise")
async def purge_ontology_noise(
    db: AsyncSession = Depends(get_db),
    _admin: UserInfo = Depends(require_admin),
):
    """옛 정책으로 DB 에 깔린 노이즈 관계를 일괄 제거.

    제거 대상 두 패턴:
      1) source='sector_match' AND confidence < 0.5
         — KSIC 산업분류 자동 매칭. 천일고속/성창기업지주 같은 무관 종목까지
           "동종업계 peer" 로 들어가 카드 그래프 노이즈의 주범.
      2) relation_type ∈ {peer, theme, macro, group} AND source='news'
         — 시황 기사("반도체 장비주들이 약세") 에서 LLM 이 잘못 잡은 peer/theme.
           새 prompt + extract_news 가드는 이걸 막지만 옛 row 들이 남아있음.

    실행 후 force re-extract 로 새 정책 (사업 본질 카테고리 + 0.5 floor) 의
    quality 있는 관계만 다시 채워짐.
    """
    from sqlalchemy import and_, delete, or_

    from app.models import StockRelation

    sector_match_low_conf = and_(
        StockRelation.source == "sector_match",
        StockRelation.confidence < 0.5,
    )
    news_shallow_type = and_(
        StockRelation.source == "news",
        StockRelation.relation_type.in_(["peer", "theme", "macro", "group"]),
    )
    # ETF / 지수 / 테마 류 — rationale 본문에 패턴 포함된 row 일괄 정리.
    # JSONB ->> 'rationale' 로 string 추출 후 ILIKE 매칭.
    rationale_text = StockRelation.extra_metadata["rationale"].astext
    etf_patterns = (
        "%etf%", "%kodex%", "%tiger%", "%ace %", "% ace%",
        "%구성종목%", "%편입%", "%지수에 포함%", "%지수 포함%",
        "%테마주%", "%관련주%", "%수혜주%", "%동반%",
    )
    rationale_etf = and_(
        StockRelation.source == "news",
        or_(*[rationale_text.ilike(p) for p in etf_patterns]),
    )

    # 2026-05-14 — LLM hallucination 가드. LLM source 인데 rationale 인용
    # 없거나 너무 짧으면 환상 가능성 ↑ (사용자가 SK하이닉스 카드에서 동화약품
    # 잡힌 case: 본문에 동화약품 0회 등장인데 LLM 이 추출). validator 새
    # 룰 이전 추출 잔재 정리.
    from sqlalchemy import func as sql_func, select
    _LLM_SRC = ["news", "sec_8k", "sec_10k_risk", "dart_contract"]
    hallucination = and_(
        StockRelation.source.in_(_LLM_SRC),
        or_(
            rationale_text.is_(None),
            sql_func.length(rationale_text) < 30,
        ),
    )

    # 2026-05-14 — target-name-in-rationale 가드. LLM source 인데 rationale 에
    # to_target Stock.name 이 없으면 환상. Python 레벨에서 정규화(공백 제거 후
    # 비교)로 처리 — SQL ILIKE 로는 한글 띄어쓰기 edge case ("SK 하이닉스"
    # vs "SK하이닉스") 를 안전하게 잡기 어렵다.
    # 아래에서 별도 Python loop 로 처리.

    to_delete_filter = or_(
        sector_match_low_conf, news_shallow_type, rationale_etf, hallucination,
    )

    # Count first 로 사용자에게 명시적 숫자 노출.

    sector_count = (
        await db.execute(
            select(sql_func.count()).select_from(StockRelation).where(sector_match_low_conf)
        )
    ).scalar() or 0
    news_count = (
        await db.execute(
            select(sql_func.count()).select_from(StockRelation).where(news_shallow_type)
        )
    ).scalar() or 0
    etf_count = (
        await db.execute(
            select(sql_func.count()).select_from(StockRelation).where(rationale_etf)
        )
    ).scalar() or 0
    hallucination_count = (
        await db.execute(
            select(sql_func.count()).select_from(StockRelation).where(hallucination)
        )
    ).scalar() or 0

    # target-name-in-rationale 필터 (Python 정규화 후 비교)
    # LLM source 행을 가져와서 to_target 의 Stock.name 이 rationale 에 없는 것을
    # 추가 delete.
    _llm_rows = (
        await db.execute(
            select(StockRelation.id, StockRelation.to_target, StockRelation.extra_metadata)
            .where(StockRelation.source.in_(_LLM_SRC))
        )
    ).all()

    # to_target ticker → Stock.name 일괄 조회
    _all_to_targets = {r.to_target for r in _llm_rows if r.to_target}
    _target_name_map: dict[str, str] = {}
    if _all_to_targets:
        _name_rows = (
            await db.execute(
                select(Stock.ticker, Stock.name).where(Stock.ticker.in_(_all_to_targets))
            )
        ).all()
        _target_name_map = {t: (n or "") for t, n in _name_rows}

    _no_target_name_ids: list[int] = []
    for row in _llm_rows:
        target_name = _target_name_map.get(row.to_target or "", "")
        if not target_name:
            continue  # DB 에 없는 ticker 는 다른 필터로 잡힘
        name_norm = "".join(target_name.split()).lower()
        ticker_norm = (row.to_target or "").lower()
        # Stock.name OR ticker 중 하나만 rationale 에 있어도 통과 — validator
        # 동일 정책. 1 자 후보는 false positive 위험으로 제외.
        candidates = [c for c in (name_norm, ticker_norm) if len(c) >= 2]
        if not candidates:
            continue  # 둘 다 1자 — 가드 무력화 (다른 필터 의존)
        meta = row.extra_metadata or {}
        rat = (meta.get("rationale") or "")
        rat_norm = "".join(rat.split()).lower()
        if not any(c in rat_norm for c in candidates):
            _no_target_name_ids.append(row.id)

    no_target_name_count = len(_no_target_name_ids)
    if _no_target_name_ids:
        await db.execute(
            delete(StockRelation).where(StockRelation.id.in_(_no_target_name_ids))
        )

    result = await db.execute(delete(StockRelation).where(to_delete_filter))
    await db.commit()
    return {
        "status": "ok",
        "deleted_total": (result.rowcount or 0) + no_target_name_count,
        "deleted_sector_match_low_conf": sector_count,
        "deleted_news_shallow_type": news_count,
        "deleted_rationale_etf_pattern": etf_count,
        "deleted_llm_hallucination_no_rationale": hallucination_count,
        "deleted_llm_no_target_name_in_rationale": no_target_name_count,
    }


@router.post("/political/purge_samples")
async def purge_political_samples(
    db: AsyncSession = Depends(get_db),
    _admin: UserInfo = Depends(require_admin),
):
    """초기 demo 단계에서 들어간 sample_macro 시드를 정리한다.

    `seed_political_sample` 엔드포인트는 example.com URL + 가상 발언 5개를
    insert 했고 (source='sample_macro'), 카드의 정치 시그널 섹션에서 사용자가
    "원문 보기" 클릭 시 example.com 으로 가는 가라 데이터로 노출됐다.
    이제 trumpstruth.org RSS 가 매시 cron 으로 자연 축적 중이라 시드 더 필요
    없음. 시드 endpoint 자체는 제거됐고 본 purge 가 잔여 정리.
    """
    from sqlalchemy import delete

    from app.models.political_signal import PoliticalSignal, PoliticalSignalTicker

    sample_ids = (
        await db.execute(
            select(PoliticalSignal.id).where(PoliticalSignal.source == "sample_macro")
        )
    ).scalars().all()
    if not sample_ids:
        return {"status": "ok", "deleted_signals": 0, "deleted_tickers": 0}

    ticker_del = await db.execute(
        delete(PoliticalSignalTicker).where(
            PoliticalSignalTicker.signal_id.in_(sample_ids)
        )
    )
    signal_del = await db.execute(
        delete(PoliticalSignal).where(PoliticalSignal.source == "sample_macro")
    )
    await db.commit()
    return {
        "status": "ok",
        "deleted_signals": signal_del.rowcount or 0,
        "deleted_tickers": ticker_del.rowcount or 0,
    }


# NOTE: 이전엔 `seed_political_sample` (POST /political/seed_sample) 가 있었고
# example.com URL 시드 5건 insert. demo 초기엔 유용했지만 trumpstruth.org 매시
# cron 정상 동작 후엔 가라 데이터로만 남아 사용자 신뢰 손상. 시드 함수 자체
# 제거 + purge_political_samples 로 잔여 정리.


@router.post("/political/purge_old")
async def purge_old_political_signals(
    days: int = 90,
    db: AsyncSession = Depends(get_db),
    _admin: UserInfo = Depends(require_admin),
):
    """`days` 일 이전 정치 시그널 row 영구 삭제 (default 90일).

    2026-05-19 — 사용자 발견 "정치 시그널 db 관리도 해야하고". 일반 row
    영원히 누적되던 정책 → retention 90일. CASCADE 로 ticker 매핑 row 도
    같이 삭제 (`PoliticalSignalTicker.signal_id` FK).

    카드 노출은 _fetch_political_signals 에서 별도 (expected_window +
    strength 기반 status 분류). 이 endpoint 는 *DB 위생* 만 담당.
    """
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    from app.models.political_signal import PoliticalSignal

    cutoff = _dt.utcnow() - _td(days=days)
    before_count = (
        await db.execute(
            select(func.count())
            .select_from(PoliticalSignal)
            .where(PoliticalSignal.posted_at < cutoff)
        )
    ).scalar() or 0
    if before_count == 0:
        return {"status": "ok", "deleted": 0, "cutoff_days": days}

    await db.execute(
        delete(PoliticalSignal).where(PoliticalSignal.posted_at < cutoff)
    )
    await db.commit()
    return {"status": "ok", "deleted": before_count, "cutoff_days": days}


@router.get("/political/status")
async def political_status(
    db: AsyncSession = Depends(get_db),
    _admin: UserInfo = Depends(require_admin),
):
    """정치 시그널 DB 상태 확인 (검증/디버깅용)."""
    from app.models.political_signal import PoliticalSignal, PoliticalSignalTicker
    from sqlalchemy import func as sql_func

    total = (
        await db.execute(select(sql_func.count()).select_from(PoliticalSignal))
    ).scalar() or 0
    analyzed = (
        await db.execute(
            select(sql_func.count())
            .select_from(PoliticalSignal)
            .where(PoliticalSignal.analyzed_at.isnot(None))
        )
    ).scalar() or 0
    relevant = (
        await db.execute(
            select(sql_func.count())
            .select_from(PoliticalSignal)
            .where(PoliticalSignal.is_market_relevant.is_(True))
        )
    ).scalar() or 0
    ticker_rows = (
        await db.execute(select(sql_func.count()).select_from(PoliticalSignalTicker))
    ).scalar() or 0
    latest = (
        await db.execute(
            select(PoliticalSignal)
            .order_by(PoliticalSignal.posted_at.desc())
            .limit(3)
        )
    ).scalars().all()
    # substantive = RT 아닌 본인 발언. 진짜 분석 대상.
    substantive = (
        await db.execute(
            select(PoliticalSignal)
            .where(~PoliticalSignal.content.like("RT:%"))
            .order_by(PoliticalSignal.posted_at.desc())
            .limit(5)
        )
    ).scalars().all()

    def _serialize(s):
        return {
            "posted_at": s.posted_at.isoformat() if s.posted_at else None,
            "content_preview": (s.content or "")[:300],
            "analyzed": s.analyzed_at is not None,
            "is_relevant": s.is_market_relevant,
            "summary_ko": s.summary_ko,
            "sentiment": s.overall_sentiment,
            "macro_themes": s.macro_themes,
            "url": s.url,
        }

    return {
        "total_signals": total,
        "analyzed": analyzed,
        "market_relevant": relevant,
        "ticker_impacts": ticker_rows,
        "latest_3": [_serialize(s) for s in latest],
        "substantive_5": [_serialize(s) for s in substantive],
    }
