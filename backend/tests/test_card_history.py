from datetime import date, datetime

from app.models.analysis import Analysis
from app.services.analyst.history import build_analysis_history, build_event_markers


def _analysis(day: date, card_data: dict) -> Analysis:
    return Analysis(
        stock_id=1,
        date=day,
        period_type="daily",
        summary="old summary",
        feedback="old feedback",
        schema_version="v2",
        card_data=card_data,
        created_at=datetime(2026, 5, day.day, 1, 0, 0),
    )


def test_build_analysis_history_summarizes_daily_cards():
    rows = [
        _analysis(
            date(2026, 5, 21),
            {
                "generated_at": "2026-05-21T01:00:00+00:00",
                "glance": {
                    "stance": "WATCH",
                    "final_grade": "B",
                    "one_line": "AI 인프라 수요는 좋지만 금리 부담",
                },
                "thesis": {"core_thesis": "Azure AI 수요가 핵심"},
                "recent_price_move": {"one_line": "최근 5거래일 +3.1% — AI 계약 기대"},
                "news": [
                    {
                        "title": "Microsoft expands AI capacity",
                        "source": "Reuters",
                        "impact": "positive",
                        "summary": "Azure AI 인프라 투자 확대",
                        "published_at": "2026-05-20T09:00:00+00:00",
                        "url": "https://example.com/msft",
                    }
                ],
            },
        )
    ]

    items = build_analysis_history(rows)

    assert len(items) == 1
    assert items[0].date == date(2026, 5, 21)
    assert items[0].stance == "WATCH"
    assert items[0].final_grade == "B"
    assert items[0].news_count == 1
    assert items[0].key_news[0].summary == "Azure AI 인프라 투자 확대"


def test_build_event_markers_extracts_price_news_and_catalysts_sorted_newest_first():
    rows = [
        _analysis(
            date(2026, 5, 21),
            {
                "recent_price_move": {
                    "primary_window": "5d",
                    "return_5d_pct": -4.2,
                    "biggest_move_date": "2026-05-20",
                    "one_line": "최근 5거래일 -4.2% — 금리 부담",
                    "causes": [
                        {
                            "text": "미국 장기 금리 상승으로 기술주 부담",
                            "confidence": "medium",
                            "evidence_date": "2026-05-20",
                        }
                    ],
                },
                "news": [
                    {
                        "title": "Azure demand remains strong",
                        "source": "Yahoo",
                        "impact": "positive",
                        "summary": "Azure 수요 강세",
                        "published_at": "2026-05-21T08:00:00+00:00",
                    }
                ],
                "thesis": {
                    "catalysts": [
                        {
                            "when": "2026-06-10",
                            "event": "실적 발표",
                            "impact_estimate": "클라우드 성장률 확인",
                            "direction": "mixed",
                        }
                    ]
                },
            },
        )
    ]

    events = build_event_markers(rows)

    assert [e.source_type for e in events] == ["catalyst", "news", "price_move"]
    assert events[0].date == date(2026, 6, 10)
    assert events[1].direction == "positive"
    assert events[2].direction == "negative"
    assert events[2].keyword == "미국 장기 금리 상승으로 기술주"


def test_build_event_markers_deduplicates_same_news_from_same_analysis():
    row = _analysis(
        date(2026, 5, 21),
        {
            "news": [
                {
                    "title": "Same title",
                    "source": "Naver",
                    "impact": "neutral",
                    "summary": "중복 뉴스",
                    "published_at": "2026-05-21T08:00:00+00:00",
                },
                {
                    "title": "Same title",
                    "source": "Naver",
                    "impact": "neutral",
                    "summary": "중복 뉴스 2",
                    "published_at": "2026-05-21T08:10:00+00:00",
                },
            ]
        },
    )

    events = build_event_markers([row])

    assert len(events) == 1
    assert events[0].title == "Same title"
