"""Public parent aliases for listed-company business units and product brands.

LLM relation extraction can name a business unit ("Google Cloud") instead of
the listed parent ("Alphabet Inc."). Those should not be shown as private
stocks. Keep this intentionally small and conservative: only map well-known
aliases whose listed parent is stable.
"""
from __future__ import annotations

import re
from typing import NamedTuple


class PublicAlias(NamedTuple):
    parent_ticker: str
    parent_name: str
    entity_kind: str = "business_unit"


_ALIASES: dict[str, PublicAlias] = {
    # Alphabet / Google
    "googlecloud": PublicAlias("GOOGL", "Alphabet Inc."),
    "googlecloude": PublicAlias("GOOGL", "Alphabet Inc."),
    "googlecloudplatform": PublicAlias("GOOGL", "Alphabet Inc."),
    "gcp": PublicAlias("GOOGL", "Alphabet Inc."),
    "youtube": PublicAlias("GOOGL", "Alphabet Inc."),
    # Amazon
    "aws": PublicAlias("AMZN", "Amazon.com, Inc."),
    "amazonwebservices": PublicAlias("AMZN", "Amazon.com, Inc."),
    # Microsoft
    "azure": PublicAlias("MSFT", "Microsoft Corporation"),
    "microsoftazure": PublicAlias("MSFT", "Microsoft Corporation"),
    # Meta
    "instagram": PublicAlias("META", "Meta Platforms, Inc."),
    "whatsapp": PublicAlias("META", "Meta Platforms, Inc."),
    # Apple
    "appstore": PublicAlias("AAPL", "Apple Inc."),
    # Oracle
    "oraclecloud": PublicAlias("ORCL", "Oracle Corporation"),
    "oraclecloudinfrastructure": PublicAlias("ORCL", "Oracle Corporation"),
    "oci": PublicAlias("ORCL", "Oracle Corporation"),
}


def _normalize_alias(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def resolve_public_alias(*values: str | None) -> PublicAlias | None:
    """Return the listed parent for a known public business-unit alias."""
    for value in values:
        alias = _ALIASES.get(_normalize_alias(value))
        if alias is not None:
            return alias
    return None

