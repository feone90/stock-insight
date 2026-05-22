from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from typing import Any

from app.models.analysis import Analysis
from app.schemas.card_history import (
    AnalysisHistoryItem,
    AnalysisHistoryNews,
    StockEventMarker,
)

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_MAX_KEY_NEWS = 3


def build_analysis_history(rows: list[Analysis]) -> list[AnalysisHistoryItem]:
    return [_history_item(row) for row in rows if isinstance(row.card_data, dict)]


def build_event_markers(rows: list[Analysis], limit: int = 80) -> list[StockEventMarker]:
    events: list[StockEventMarker] = []
    for row in rows:
        if not isinstance(row.card_data, dict):
            continue
        events.extend(_price_move_events(row))
        events.extend(_news_events(row))
        events.extend(_catalyst_events(row))

    deduped: dict[str, StockEventMarker] = {}
    for event in events:
        key = f"{event.date.isoformat()}|{event.source_type}|{event.title[:80]}"
        if key not in deduped:
            deduped[key] = event

    return sorted(
        deduped.values(),
        key=lambda e: (e.date, e.source_type, e.title),
        reverse=True,
    )[: max(1, min(limit, 200))]


def _history_item(row: Analysis) -> AnalysisHistoryItem:
    card = row.card_data or {}
    glance = card.get("glance") or {}
    thesis = card.get("thesis") or {}
    news = [n for n in (card.get("news") or []) if isinstance(n, dict)]
    price_move = card.get("recent_price_move") or {}

    return AnalysisHistoryItem(
        date=_row_date(row),
        generated_at=_parse_datetime(card.get("generated_at")) or row.created_at,
        stance=glance.get("stance"),
        final_grade=glance.get("final_grade"),
        one_line=_clean(glance.get("one_line")) or _clean(row.summary) or "분석 요약 없음",
        thesis=_clean(thesis.get("core_thesis")),
        price_move=_clean(price_move.get("one_line")) if isinstance(price_move, dict) else None,
        news_count=len(news),
        key_news=[
            AnalysisHistoryNews(
                title=_clean(n.get("title")) or "제목 없음",
                source=_clean(n.get("source")) or "출처 없음",
                impact=_normalize_direction(n.get("impact")),
                summary=_clean(n.get("summary")) or _clean(n.get("title")) or "요약 없음",
                published_at=_parse_datetime(n.get("published_at")),
                url=_clean(n.get("url")),
            )
            for n in news[:_MAX_KEY_NEWS]
        ],
    )


def _price_move_events(row: Analysis) -> list[StockEventMarker]:
    card = row.card_data or {}
    move = card.get("recent_price_move") or {}
    if not isinstance(move, dict) or not move:
        return []

    analysis_date = _row_date(row)
    event_date = (
        _parse_date(move.get("biggest_move_date"))
        or _first_cause_date(move)
        or analysis_date
    )
    primary_window = move.get("primary_window") or "5d"
    pct = move.get(f"return_{primary_window}_pct")
    direction = _direction_from_pct(pct)
    one_line = _clean(move.get("one_line")) or "가격 움직임 원인"
    causes = [c for c in (move.get("causes") or []) if isinstance(c, dict)]
    if not one_line and not causes:
        return []

    summary = " · ".join(
        _clean(c.get("text")) for c in causes[:2] if _clean(c.get("text"))
    ) or one_line
    confidence = causes[0].get("confidence") if causes else None
    return [
        StockEventMarker(
            id=_event_id(analysis_date, event_date, "price_move", one_line),
            date=event_date,
            source_type="price_move",
            direction=direction,
            title=one_line,
            summary=summary,
            keyword=_keyword_from_text(summary or one_line),
            confidence=_clean(confidence),
            source_label="가격 움직임",
            url=None,
            analysis_date=analysis_date,
        )
    ]


def _news_events(row: Analysis) -> list[StockEventMarker]:
    card = row.card_data or {}
    analysis_date = _row_date(row)
    events: list[StockEventMarker] = []
    for n in [x for x in (card.get("news") or []) if isinstance(x, dict)]:
        event_date = _parse_date(n.get("published_at")) or analysis_date
        title = _clean(n.get("title")) or "뉴스"
        summary = _clean(n.get("why_it_matters")) or _clean(n.get("summary")) or title
        impact = _normalize_direction(n.get("impact"))
        events.append(
            StockEventMarker(
                id=_event_id(analysis_date, event_date, "news", title),
                date=event_date,
                source_type="news",
                direction=impact,
                title=title,
                summary=summary,
                keyword=_keyword_from_text(summary),
                confidence=None,
                source_label=_clean(n.get("source")) or "뉴스",
                url=_clean(n.get("url")),
                analysis_date=analysis_date,
            )
        )
    return events


def _catalyst_events(row: Analysis) -> list[StockEventMarker]:
    card = row.card_data or {}
    thesis = card.get("thesis") or {}
    analysis_date = _row_date(row)
    events: list[StockEventMarker] = []
    for c in [x for x in (thesis.get("catalysts") or []) if isinstance(x, dict)]:
        event_date = _parse_date(c.get("when")) or analysis_date
        event = _clean(c.get("event")) or "예정 이벤트"
        impact = _clean(c.get("impact_estimate")) or event
        direction = _normalize_direction(c.get("direction"))
        events.append(
            StockEventMarker(
                id=_event_id(analysis_date, event_date, "catalyst", event),
                date=event_date,
                source_type="catalyst",
                direction=direction,
                title=event,
                summary=impact,
                keyword=_keyword_from_text(event),
                confidence=None,
                source_label="예정 이벤트",
                url=None,
                analysis_date=analysis_date,
            )
        )
    return events


def _row_date(row: Analysis) -> date:
    if isinstance(row.date, date):
        return row.date
    return _parse_date(row.date) or date.today()


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    match = _DATE_RE.search(value)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(0))
    except ValueError:
        return None


def _first_cause_date(move: dict[str, Any]) -> date | None:
    for cause in move.get("causes") or []:
        if isinstance(cause, dict):
            parsed = _parse_date(cause.get("evidence_date"))
            if parsed:
                return parsed
    return None


def _direction_from_pct(pct: Any) -> str:
    try:
        value = float(pct)
    except (TypeError, ValueError):
        return "neutral"
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def _normalize_direction(value: Any) -> str:
    if value in {"positive", "negative", "mixed", "neutral"}:
        return value
    if value in {"bullish", "upside"}:
        return "positive"
    if value in {"bearish", "downside"}:
        return "negative"
    return "neutral"


def _keyword_from_text(text: str) -> str:
    cleaned = _clean(text)
    if not cleaned:
        return "이벤트"
    for sep in (" — ", " - ", "·", "+", ","):
        if sep in cleaned:
            cleaned = cleaned.split(sep, 1)[0]
            break
    return cleaned.strip()[:18].strip() or "이벤트"


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _event_id(analysis_date: date, event_date: date, kind: str, title: str) -> str:
    raw = f"{analysis_date.isoformat()}|{event_date.isoformat()}|{kind}|{title}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
