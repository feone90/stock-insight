"""뉴스/공시 데이터를 LLM으로 분석하여 키워드를 생성한다."""

import json
import logging
from datetime import date, timedelta

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Stock
from app.models.analysis import Analysis, KeywordDetail, DailyKeyword
from app.models.news import News
from app.models.disclosure import Disclosure
from app.services.llm.adapter import LLMAdapter
from app.services.llm.prompts import build_analysis_prompt

logger = logging.getLogger(__name__)

ANALYSIS_PERIOD_TYPE = "daily"
NEWS_LOOKBACK_DAYS = 7


async def analyze_stock(db: AsyncSession, stock: Stock, adapter: LLMAdapter) -> dict:
    """종목의 뉴스/공시를 LLM으로 분석하여 키워드를 생성한다.

    Returns:
        {"analysis_created": True} 또는 {"analysis_created": False, "error": "..."}
    """
    try:
        # 1. 최근 뉴스 조회
        since = date.today() - timedelta(days=NEWS_LOOKBACK_DAYS)
        news_result = await db.execute(
            select(News)
            .where(News.stock_id == stock.id, News.published_at >= since)
            .order_by(News.published_at.desc())
        )
        news_rows = news_result.scalars().all()

        # 2. 최근 공시 조회
        disc_result = await db.execute(
            select(Disclosure)
            .where(Disclosure.stock_id == stock.id, Disclosure.disclosed_at >= since)
            .order_by(Disclosure.disclosed_at.desc())
        )
        disc_rows = disc_result.scalars().all()

        # 뉴스/공시 둘 다 없으면 스킵
        if not news_rows and not disc_rows:
            return {"analysis_created": False, "error": "분석할 뉴스/공시 없음"}

        # 3. 프롬프트 생성
        news_list = [
            {
                "title": n.title,
                "published_at": n.published_at.strftime("%Y-%m-%d") if n.published_at else "",
                "source": n.source or "",
                "url": n.url or "",
            }
            for n in news_rows
        ]
        disc_list = [
            {
                "title": d.title,
                "disclosed_at": d.disclosed_at.strftime("%Y-%m-%d") if d.disclosed_at else "",
                "disclosure_type": d.disclosure_type or "",
            }
            for d in disc_rows
        ]

        prompt = build_analysis_prompt(
            stock_name=stock.name,
            ticker=stock.ticker,
            market=stock.market,
            current_price=stock.current_price,
            change_percent=stock.change_percent,
            news_list=news_list,
            disclosure_list=disc_list,
        )

        # 4. LLM 호출
        raw = await adapter.generate_json(prompt)

        # 5. JSON 파싱
        data = _parse_llm_response(raw)

        # 6. source에 뉴스 URL 매칭
        _match_source_urls(data, news_list)

        # 7. DB 저장 (기존 분석 교체)
        await _save_analysis(db, stock.id, data)

        return {"analysis_created": True}

    except json.JSONDecodeError as e:
        logger.warning("LLM JSON 파싱 실패 [%s]: %s", stock.ticker, e)
        return {"analysis_created": False, "error": f"LLM 응답 JSON 파싱 실패: {e}"}
    except Exception as e:
        logger.warning("분석 실패 [%s]: %s", stock.ticker, e)
        return {"analysis_created": False, "error": f"분석 실패: {e}"}


def _parse_llm_response(raw: str) -> dict:
    """LLM 응답을 파싱한다. JSON 블록 추출 + 검증."""
    text = raw.strip()
    # markdown code fence 제거
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    data = json.loads(text)

    # 필수 필드 검증
    if "keywords" not in data:
        data["keywords"] = []
    if "daily_keywords" not in data:
        data["daily_keywords"] = []
    if "summary" not in data:
        data["summary"] = ""
    if "feedback" not in data:
        data["feedback"] = ""

    # keyword type 검증
    valid_types = {"bullish", "bearish", "neutral"}
    valid_impacts = {"high", "mid", "low"}
    valid_durations = {"short", "mid", "long"}

    for kw in data["keywords"]:
        if kw.get("type") not in valid_types:
            kw["type"] = "neutral"
        if kw.get("impact_level") not in valid_impacts:
            kw["impact_level"] = "mid"
        if kw.get("duration") not in valid_durations:
            kw["duration"] = "mid"

    for dk in data["daily_keywords"]:
        if dk.get("type") not in valid_types:
            dk["type"] = "neutral"

    return data


def _match_source_urls(data: dict, news_list: list[dict]) -> None:
    """LLM이 출력한 source(기사 제목)를 뉴스 URL로 교체한다."""
    if not news_list:
        return
    for kw in data.get("keywords", []):
        source = kw.get("source", "")
        if source.startswith("http"):
            continue  # 이미 URL이면 스킵
        # 제목 부분 매칭으로 URL 찾기
        for news in news_list:
            title = news.get("title", "")
            url = news.get("url", "")
            if not url:
                continue
            # source 텍스트가 뉴스 제목에 포함되거나, 뉴스 제목이 source에 포함
            if (title and source and
                (title in source or source in title or
                 title[:15] in source or source[:15] in title)):
                kw["source"] = url
                break


async def _save_analysis(db: AsyncSession, stock_id: int, data: dict) -> None:
    """분석 결과를 DB에 저장한다. 동일 날짜 기존 분석은 교체."""
    today = date.today()

    # 기존 동일 날짜 분석 삭제 (cascade로 keywords, daily_keywords도 삭제)
    existing = await db.execute(
        select(Analysis).where(
            Analysis.stock_id == stock_id,
            Analysis.date == today,
            Analysis.period_type == ANALYSIS_PERIOD_TYPE,
        )
    )
    for old in existing.scalars().all():
        await db.delete(old)
    await db.flush()  # 삭제 반영 후 insert

    # 새 분석 생성
    analysis = Analysis(
        stock_id=stock_id,
        date=today,
        period_type=ANALYSIS_PERIOD_TYPE,
        summary=data.get("summary", ""),
        feedback=data.get("feedback", ""),
    )
    db.add(analysis)
    await db.flush()  # analysis.id 확보

    # 키워드 저장
    for kw in data.get("keywords", []):
        db.add(KeywordDetail(
            analysis_id=analysis.id,
            keyword=kw.get("keyword", "")[:100],
            type=kw.get("type", "neutral"),
            detail=kw.get("detail", ""),
            source=kw.get("source", ""),
            impact_level=kw.get("impact_level", "mid"),
            duration=kw.get("duration", "mid"),
        ))

    # 일별 키워드 저장
    for dk in data.get("daily_keywords", []):
        dk_date = dk.get("date")
        try:
            parsed_date = date.fromisoformat(dk_date) if dk_date else today
        except (ValueError, TypeError):
            parsed_date = today

        db.add(DailyKeyword(
            analysis_id=analysis.id,
            date=parsed_date,
            keyword=dk.get("keyword", "")[:100],
            type=dk.get("type", "neutral"),
        ))

    await db.commit()
