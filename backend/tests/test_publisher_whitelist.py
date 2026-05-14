"""publisher_whitelist — KR/US 신뢰 매체 host suffix 매칭 검증.

Codex 시니어 트레이더 리뷰(2026-05-14) 권고 적용. 블로그·스팸·aggregator는
drop, 정통 매체 + 증권 전문지 + 외신은 keep. 서브도메인(biz.chosun.com)도
suffix 매칭으로 통과해야 함.
"""
import pytest

from app.collectors.publisher_whitelist import (
    _extract_host,
    is_trusted_kr,
    is_trusted_us,
)


# ── _extract_host: URL → lowercase host (www 제거)


@pytest.mark.parametrize("url,expected", [
    ("https://www.hankyung.com/article/123", "hankyung.com"),
    ("https://biz.chosun.com/news/abc", "biz.chosun.com"),
    ("HTTPS://www.WSJ.com/article", "wsj.com"),
    ("https://news.naver.com/main/read", "news.naver.com"),
    ("not-a-url", ""),
    ("", ""),
    ("https://", ""),
])
def test_extract_host(url, expected):
    assert _extract_host(url) == expected


# ── KR whitelist


@pytest.mark.parametrize("url", [
    "https://www.hankyung.com/article/2026051401",
    "https://biz.chosun.com/site/data/html/1234.html",  # 서브도메인
    "https://www.mk.co.kr/news/economy/2026/05/14/abc",
    "http://www.yna.co.kr/view/AKR20260514",
    "https://news.naver.com/main/read.nhn?oid=015&aid=0005286652",
    "https://n.news.naver.com/mnews/article/011/0004620485",  # 모바일 서브
    "https://www.bloomberg.com/news/articles/2026-05-14/kr-update",  # 외신 KR
    "https://www.fnnews.com/news/202605141200",
    "https://www.einfomax.co.kr/news/articleView.html?idxno=999",
])
def test_kr_trusted_passes(url):
    assert is_trusted_kr(url) is True


@pytest.mark.parametrize("url", [
    "https://blog.naver.com/foo/bar",                  # 네이버블로그
    "https://example.tistory.com/post/123",            # 티스토리
    "https://m.blog.daum.net/abc",                     # 다음블로그
    "https://www.spam-aggregator.kr/article/1",        # 임의 스팸
    "https://www.pinpointnews.co.kr/news/abc",         # 화이트리스트 미포함 (5/13 ETF noise 케이스)
    "https://www.insightkorea.co.kr/news/abc",         # 화이트리스트 미포함
    "https://www.cbci.co.kr/news/abc",                 # 화이트리스트 미포함
    "https://www.cnbc.com/2026/05/14/abc",             # US 매체 — KR 시장엔 별개
    "",                                                # 빈 URL
])
def test_kr_untrusted_dropped(url):
    assert is_trusted_kr(url) is False


# ── US whitelist


@pytest.mark.parametrize("url", [
    "https://www.bloomberg.com/news/articles/2026-05-14/abc",
    "https://www.reuters.com/business/finance/abc",
    "https://www.wsj.com/articles/123",
    "https://www.cnbc.com/2026/05/14/abc",
    "https://www.marketwatch.com/story/abc",
    "https://seekingalpha.com/article/abc",
    "https://finance.yahoo.com/news/abc",                # 서브도메인
    "https://www.businesswire.com/news/home/abc",        # 회사 PR
    "https://www.sec.gov/Archives/edgar/data/...",       # EDGAR
])
def test_us_trusted_passes(url):
    assert is_trusted_us(url) is True


@pytest.mark.parametrize("url", [
    "https://medium.com/@trader/abc",
    "https://substack.com/@author/article",
    "https://www.investorvillage.com/foo",
    "https://www.gurufocus.com/article",
    "https://www.hankyung.com/article",                  # KR 매체 — US엔 별개
    "https://blog.naver.com/us-stock/abc",
    "",
])
def test_us_untrusted_dropped(url):
    assert is_trusted_us(url) is False
