"""뉴스 publisher 신뢰 매체 whitelist — KR/US 별도.

Codex 시니어 트레이더 리뷰(2026-05-14): "Naver Open News API should not be
KR primary without publisher whitelisting; keep it only as a recall layer
behind Google News RSS and direct publisher RSS."

Approach: 모든 KR/US 뉴스 collector 결과를 DB insert 전 host 기반
whitelist로 필터링. 정통 매체 + 증권 전문지 + 외신만 통과. 블로그·SEO 스팸·
aggregator·티스토리·네이버블로그 등은 자동 drop. quota는 그대로 쓰되 trust
layer만 추가.

KR 일간지/증권 전문지 + 통신사 + 외신 KR 지점. 의심 매체는 보수적으로 포함
시키지 말고 누락. 카드에 0건 노출되는 것보단 noise 노출이 더 큰 손해.
"""
from __future__ import annotations

from urllib.parse import urlparse


# KR 정통 매체 — 증권/경제 전문지 + 종합지 + 통신사 + 외신 KR.
# 도메인은 host suffix 매칭이라 서브도메인(biz.chosun.com 등) 자동 포함.
KR_TRUSTED: frozenset[str] = frozenset({
    # 경제·증권 전문지
    "hankyung.com",         # 한국경제
    "mk.co.kr",             # 매일경제
    "mt.co.kr",             # 머니투데이
    "edaily.co.kr",         # 이데일리
    "einfomax.co.kr",       # 연합인포맥스
    "sedaily.com",          # 서울경제
    "fnnews.com",           # 파이낸셜뉴스
    "asiae.co.kr",          # 아시아경제
    "heraldcorp.com",       # 헤럴드경제
    "ajunews.com",          # 아주경제
    "newspim.com",          # 뉴스핌
    "bizwatch.co.kr",       # 비즈워치
    "the-stock.kr",         # 더스탁
    "thebell.co.kr",        # 더벨
    # 통신사
    "yna.co.kr",            # 연합뉴스
    "yonhapnews.co.kr",
    "news1.kr",             # 뉴스1
    "newsis.com",           # 뉴시스
    # 종합지
    "chosun.com",           # 조선일보 (서브: biz.chosun.com)
    "joongang.co.kr",       # 중앙일보
    "donga.com",            # 동아일보
    "hani.co.kr",           # 한겨레
    "khan.co.kr",           # 경향신문
    "kmib.co.kr",           # 국민일보
    "seoul.co.kr",          # 서울신문
    "munhwa.com",           # 문화일보
    # 외신 KR 지점/번역
    "reuters.com",
    "bloomberg.com",
    "wsj.com",
    "ft.com",
    "nikkei.com",
    # 네이버/구글 자체 게이트 (실제 매체 link로 redirect)
    "news.naver.com",       # 네이버 뉴스 ID URL — 매체 article 페이지
    "n.news.naver.com",
    "finance.naver.com",    # 네이버 증권 종목별 큐레이션 (entity matching 정확)
    "news.google.com",      # 구글 뉴스 RSS link
})

# US 정통 매체 — 경제 전문지 + 종합지 + 산업 전문 + 통신사 + 회사 PR.
US_TRUSTED: frozenset[str] = frozenset({
    # 경제·증권 전문지
    "bloomberg.com",
    "reuters.com",
    "wsj.com",
    "ft.com",
    "cnbc.com",
    "marketwatch.com",
    "barrons.com",
    "investors.com",        # IBD
    "morningstar.com",
    "zacks.com",
    "seekingalpha.com",
    "benzinga.com",
    "fool.com",             # Motley Fool
    "thestreet.com",
    "kiplinger.com",
    # 일반·비즈니스
    "forbes.com",
    "businessinsider.com",
    "fortune.com",
    "economist.com",
    "bizjournals.com",
    # 통신사
    "ap.org",
    "apnews.com",
    "axios.com",
    # 큰 종합지
    "nytimes.com",
    "washingtonpost.com",
    "theguardian.com",
    # 산업 전문 (tech/AI/반도체 — US 종목 핵심)
    "theinformation.com",
    "techcrunch.com",
    "engadget.com",
    "venturebeat.com",
    "anandtech.com",
    "tomshardware.com",
    "semianalysis.com",
    # 회사 PR (8-K 동급 신뢰)
    "businesswire.com",
    "prnewswire.com",
    "globenewswire.com",
    "sec.gov",
    # Yahoo (yfinance 출력 매체)
    "yahoo.com",
    "finance.yahoo.com",
    # Investing.com (영문)
    "investing.com",
})


def _extract_host(url: str) -> str:
    """URL → lowercase host (www. 프리픽스 제거)."""
    if not url:
        return ""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""
    return host.removeprefix("www.")


def _is_trusted(host: str, trusted: frozenset[str]) -> bool:
    """host가 trusted 도메인 또는 그 서브도메인이면 True."""
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in trusted)


def is_trusted_kr(url: str) -> bool:
    return _is_trusted(_extract_host(url), KR_TRUSTED)


def is_trusted_us(url: str) -> bool:
    return _is_trusted(_extract_host(url), US_TRUSTED)
