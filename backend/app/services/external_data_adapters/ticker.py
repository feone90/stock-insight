"""Ticker normalization + market routing.

Frontend / favorites / seed / search receive raw form (Yahoo `.KS` suffix,
`KRX:` prefix, lowercase US tickers). Adapters never accept raw form — all
inbound paths go through `normalize_ticker` first.
"""
from __future__ import annotations

import re

from app.services.external_data_adapters.base import Market

_KR_PATTERN = re.compile(r"^\d{6}$")
_US_PATTERN = re.compile(r"^[A-Z]{1,5}$")
_SUFFIX_RE = re.compile(r"\.(KS|KQ|KX)$|^KRX:", re.IGNORECASE)


def normalize_ticker(raw: str) -> tuple[str, Market]:
    """Yahoo/KRX 형식 변형을 정규화 + 시장 분기.

    Examples:
        '005930'        → ('005930', 'KR')
        '005930.KS'     → ('005930', 'KR')
        'KRX:005930'    → ('005930', 'KR')
        'TSLA'          → ('TSLA', 'US')
        'tsla'          → ('TSLA', 'US')
        '005930.US'     → ValueError
        '12345'         → ValueError  (5자리)
    """
    s = _SUFFIX_RE.sub("", raw.strip()).upper()
    if _KR_PATTERN.match(s):
        return s, "KR"
    if _US_PATTERN.match(s):
        return s, "US"
    raise ValueError(f"unknown ticker format: {raw!r}")
