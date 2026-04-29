"""Shared constants for external data adapters.

Centralized so magic numbers aren't sprinkled across adapter implementations
and their sources stay traceable.
"""
from __future__ import annotations

# SIC → GICS confidence (sec_edgar_adapter.fetch_sector).
# SIC (1980s 4-digit US Census taxonomy) is coarser than GICS, so even a clean
# mapping carries uncertainty; an unmapped code is essentially "Unknown".
SIC_MAPPING_HIT_CONFIDENCE = 0.7
SIC_MAPPING_MISS_CONFIDENCE = 0.3

# SEC EDGAR rate limit per https://www.sec.gov/os/accessing-edgar-data.
# We stay well under for family-use traffic; documented ceiling for prewarm sizing.
SEC_RATE_LIMIT_PER_SEC = 10

# Result cache (cache.py).
CACHE_MAX_SIZE = 8       # ResultCache LRU cap; > PREWARM_LIMIT so prewarm cannot self-evict.
CACHE_TTL_SEC = 600      # Aligned with dartlab's own internal _CACHE_TTL.

# Prewarm (prewarm.py).
PREWARM_LIMIT = 5        # Top-N favorites fetched at app start.

# Ticker → CIK cache (sec_edgar_adapter, sec_company_tickers.json).
TICKER_CIK_CACHE_TTL_SEC = 86400  # 24h
