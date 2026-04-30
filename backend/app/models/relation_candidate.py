"""Relation candidate buffer (P1.6 v0).

Holds extracted (from, to) pairs where one or both tickers are not yet in the
Reference Universe (Tier 1 or Tier 2). When P1.7 promotes a Tier 3 stock
(user-touched), `scan_pending_candidates(stock_id)` scans this table for rows
whose other side is also in the universe and migrates them to `stock_relations`.

Plan: docs/superpowers/plans/2026-04-30-p1.6-relation-extraction.md §5.3
Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §4
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.stock import Base


class RelationCandidate(Base):
    __tablename__ = "relation_candidates"
    __table_args__ = (
        # `WHERE promoted_at IS NULL` partial index — pending scan is the hot path.
        Index(
            "ix_candidates_pending",
            "promoted_at",
            postgresql_where="promoted_at IS NULL",
        ),
        Index("ix_candidates_from_ticker", "from_ticker"),
        Index("ix_candidates_to_ticker", "to_ticker"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    from_ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    to_ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    signal_direction: Mapped[str] = mapped_column(
        String(20), nullable=False, default="positive"
    )
    strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    promoted_to_relation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("stock_relations.id"), nullable=True
    )
