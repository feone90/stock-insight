"""LLM 프롬프트 템플릿."""

ANALYSIS_JSON_SCHEMA = """{
  "keywords": [
    {
      "keyword": "키워드 이름",
      "type": "bullish | bearish | neutral",
      "detail": "상세 설명 (1-2문장)",
      "source": "출처 (뉴스 제목 또는 공시명)",
      "impact_level": "high | mid | low",
      "duration": "short | mid | long"
    }
  ],
  "daily_keywords": [
    {
      "date": "YYYY-MM-DD",
      "keyword": "키워드 이름",
      "type": "bullish | bearish | neutral"
    }
  ],
  "summary": "종합 요약 (2-3문장)",
  "feedback": "중장기 투자자를 위한 피드백/전략 (2-3문장)"
}"""

MAX_NEWS_ITEMS = 20


def build_analysis_prompt(
    stock_name: str,
    ticker: str,
    market: str,
    current_price: float | None,
    change_percent: float | None,
    news_list: list[dict],
    disclosure_list: list[dict],
) -> str:
    """뉴스/공시 데이터로 분석 프롬프트를 생성한다."""
    # 뉴스 truncate
    truncated_news = news_list[:MAX_NEWS_ITEMS]
    news_text = "\n".join(
        f"- [{n.get('published_at', '')}] {n.get('title', '')} (출처: {n.get('source', '')})"
        for n in truncated_news
    )
    if not news_text:
        news_text = "(뉴스 없음)"

    disc_text = "\n".join(
        f"- [{d.get('disclosed_at', '')}] {d.get('title', '')} ({d.get('disclosure_type', '')})"
        for d in disclosure_list
    )
    if not disc_text:
        disc_text = "(공시 없음)"

    price_info = ""
    if current_price is not None:
        price_info = f"- 최근 주가: {current_price:,.0f}"
        if change_percent is not None:
            price_info += f" ({change_percent:+.2f}%)"

    return f"""당신은 주식 분석 전문가입니다. 아래 데이터를 분석해서 JSON 형식으로만 응답하세요.

## 종목 정보
- 종목: {stock_name} ({ticker})
- 시장: {market}
{price_info}

## 최근 뉴스 ({len(truncated_news)}건)
{news_text}

## 최근 공시 ({len(disclosure_list)}건)
{disc_text}

## 요청
1. 상승/하락/보합 요인을 키워드로 추출하세요 (각 최대 5개)
2. 각 키워드에 상세설명, 출처, 영향도(high/mid/low), 지속성(short/mid/long)을 포함하세요
3. 일별 대표 키워드를 매핑하세요 (뉴스 날짜 기준, 최근 7일)
4. 종합 요약을 작성하세요 (2-3문장)
5. 중장기 투자자를 위한 피드백/전략을 작성하세요 (2-3문장)

type은 반드시 "bullish", "bearish", "neutral" 중 하나를 사용하세요.
impact_level은 "high", "mid", "low" 중 하나를 사용하세요.
duration은 "short", "mid", "long" 중 하나를 사용하세요.

반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만 출력하세요.

{ANALYSIS_JSON_SCHEMA}"""
