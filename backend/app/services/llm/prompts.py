"""LLM 프롬프트 템플릿."""

ANALYSIS_JSON_SCHEMA = """{
  "keywords": [
    {
      "keyword": "핵심 키워드 (4-8글자)",
      "type": "bullish | bearish | neutral",
      "detail": "이 요인이 주가에 미치는 구체적 영향. 수치, 비교, 타임라인 포함. 3-5문장.",
      "source": "근거 뉴스의 URL (http로 시작). 없으면 기사 제목.",
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
  "summary": "이번 주 종합 요약 (4-5문장)",
  "feedback": "투자 전략 및 액션 플랜 (4-5문장)"
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

    return f"""당신은 증권사 리서치센터의 시니어 애널리스트입니다.
개인 투자자의 실제 매매 판단에 직접 사용될 분석을 작성합니다.
뻔한 일반론이 아닌, 이 종목에 특화된 구체적이고 날카로운 인사이트를 제공하세요.

## 종목 정보
- 종목: {stock_name} ({ticker})
- 시장: {market}
{price_info}

## 최근 뉴스 ({len(truncated_news)}건)
{news_text}

## 최근 공시 ({len(disclosure_list)}건)
{disc_text}

## 분석 지침

### keywords — 최소 8개, 최대 15개
상승/하락/보합 각 카테고리에서 최소 2개 이상 추출하세요.
같은 뉴스라도 다른 각도에서 여러 키워드를 뽑을 수 있습니다.

각 키워드에 대해:
- **keyword**: 투자자가 3초 만에 이해하는 4-8글자 (예: "HBM3E 양산 본격화", "美 관세 리스크", "배당금 상향")
- **detail**: 이 요인이 주가에 미치는 구체적 영향을 분석하세요.
  - 반드시 수치를 포함 (매출 전망, 시장 점유율, 목표가 등)
  - 경쟁사 대비 비교 (삼성 vs SK하이닉스, 테슬라 vs BYD 등)
  - 시간축 명시 (단기 1-2주 vs 중기 1-3개월 vs 장기 효과)
  - 3-5문장으로 작성
- **source**: 근거가 된 뉴스의 URL을 그대로 넣으세요. URL 없으면 기사 제목.
- **impact_level**: high(주가 5%+ 영향), mid(1-5%), low(1% 미만)
- **duration**: short(1주 이내), mid(1-3개월), long(3개월+)

### daily_keywords — 뉴스가 있는 각 날짜마다 1-2개
뉴스 발행일 기준으로 각 날짜의 핵심 이벤트를 매핑하세요.

### summary — 4-5문장
- 이번 기간 주가 흐름의 핵심 드라이버
- 가장 중요한 이벤트 2-3개를 구체적으로 언급
- 시장 대비 상대적 강약 판단

### feedback — 4-5문장, 실전 투자 전략
- 매수/매도/관망 중 하나를 명확히 권고하고 이유 제시
- 적정 매수 구간 또는 손절 기준을 수치로 제시
- 향후 1-3개월 내 주의할 이벤트 (실적 발표, 배당, 정책 등)
- 포트폴리오 내 비중 조절 가이드

## 출력 규칙
- type: "bullish", "bearish", "neutral" 중 하나만
- impact_level: "high", "mid", "low" 중 하나만
- duration: "short", "mid", "long" 중 하나만
- 반드시 JSON만 출력. 다른 텍스트 없이.

{ANALYSIS_JSON_SCHEMA}"""
