"""LLM 프롬프트 템플릿."""

ANALYSIS_JSON_SCHEMA = """{
  "keywords": [
    {
      "keyword": "핵심 키워드 (4-8글자)",
      "type": "bullish | bearish | neutral",
      "detail": "구체적인 분석 내용. 수치와 맥락을 포함하여 3-4문장으로 작성.",
      "source": "출처 뉴스 기사의 URL (http로 시작). URL이 없으면 기사 제목.",
      "impact_level": "high | mid | low",
      "duration": "short | mid | long"
    }
  ],
  "daily_keywords": [
    {
      "date": "YYYY-MM-DD",
      "keyword": "그날의 핵심 키워드",
      "type": "bullish | bearish | neutral"
    }
  ],
  "summary": "이번 주 종합 요약. 주가 흐름과 핵심 이벤트를 3-4문장으로.",
  "feedback": "중장기 투자자를 위한 구체적 전략. 매수/매도/관망 판단 근거와 주의할 리스크를 3-4문장으로."
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
    truncated_news = news_list[:MAX_NEWS_ITEMS]
    news_text = "\n".join(
        f"- [{n.get('published_at', '')}] {n.get('title', '')} (출처: {n.get('source', '')}) URL: {n.get('url', '')}"
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

    return f"""당신은 한국의 주식 전문 애널리스트입니다. 아래 뉴스/공시 데이터를 심층 분석하여 JSON으로 응답하세요.

## 종목 정보
- 종목: {stock_name} ({ticker})
- 시장: {market}
{price_info}

## 최근 뉴스 ({len(truncated_news)}건)
{news_text}

## 최근 공시 ({len(disclosure_list)}건)
{disc_text}

## 분석 지침

### keywords (상승/하락/보합 요인)
- 뉴스를 종합하여 주가에 영향을 미치는 핵심 요인을 추출하세요
- 각 요인별로 최대 5개씩 (bullish/bearish/neutral)
- **keyword**: 투자자가 한눈에 이해할 수 있는 4-8글자 키워드 (예: "HBM 수주 확대", "환율 급등 부담")
- **detail**: 해당 요인이 주가에 미치는 영향을 구체적 수치와 맥락을 포함하여 3-4문장으로 설명
- **source**: 근거가 된 뉴스의 URL을 그대로 넣으세요 (http로 시작하는 전체 URL). URL이 없으면 기사 제목
- **impact_level**: 주가 영향도 (high: 5%+ 변동 가능, mid: 1-5%, low: 1% 미만)
- **duration**: 영향 지속 기간 (short: 1주 이내, mid: 1-3개월, long: 3개월 이상)

### daily_keywords (일별 대표 키워드)
- 뉴스 날짜 기준으로 최근 7일간 각 날짜의 대표 키워드 1개씩 매핑

### summary (종합 요약)
- 이번 주 해당 종목의 주가 흐름과 핵심 이벤트를 3-4문장으로 요약

### feedback (투자 전략)
- 중장기 투자자(6개월-1년 관점) 기준 구체적 전략 제시
- 매수/매도/관망 중 하나를 명확히 권고하고 근거 제시
- 주의해야 할 리스크 요인도 언급

## 출력 규칙
- type: "bullish", "bearish", "neutral" 중 하나만 사용
- impact_level: "high", "mid", "low" 중 하나만 사용
- duration: "short", "mid", "long" 중 하나만 사용
- 반드시 JSON만 출력. 다른 텍스트 없이.

{ANALYSIS_JSON_SCHEMA}"""
