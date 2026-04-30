from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.stock import Base


class StockRelation(Base):
    """An ontology edge: from_stock --[type]--> to_target.

    `to_target` may be a Stock (FK by ticker stored as string) OR a virtual node
    (theme/macro factor). Hence string column not FK — virtual nodes don't have
    a row in `stocks`.

    P1.6 v0 expansion (spec §4 / plan §5):
      - `signal_direction` — positive / negative / inverse (zero-sum competitor)
      - `confidence` — data source trust (separate from `strength` = relation magnitude)
      - `valid_from` / `valid_until` / `is_active` — temporal validity (contract terms)
      - `metadata` — JSONB freeform (value_krw, term_months, source_url, ...)

    `relation_type` (11 types):
      peer / supply_upstream / supply_downstream / group / theme / macro /
      competitor / contract_supplier / contract_customer / complementary /
      regulatory_link
    """

    __tablename__ = "stock_relations"
    __table_args__ = (
        # Source is part of the unique tuple so concurrent writers (auto
        # post-save hook + llm_web_search bg refresh) can persist the same
        # (from, to, type) edge in parallel rows. Spec §9.
        UniqueConstraint(
            "from_stock_id", "to_target", "relation_type", "source",
            name="uq_relation_triple",
        ),
        Index("ix_relations_from", "from_stock_id"),
        Index("ix_relations_target", "to_target"),
        # P1.6 v0: top-N "strongest peers" sort uses (strength * confidence) DESC
        # within from_stock_id. Composite covers the hot card-relations query.
        Index(
            "ix_relations_from_signal_score",
            "from_stock_id",
            "signal_direction",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    to_target: Mapped[str] = mapped_column(String(100))  # ticker OR theme name OR factor name
    to_kind: Mapped[str] = mapped_column(String(20))  # "stock" | "theme" | "macro"
    relation_type: Mapped[str] = mapped_column(String(30))

    strength: Mapped[float] = mapped_column(Float, default=0.5)  # 0..1 relation magnitude
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="llm-curation")
    discovered_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # P1.6 v0 expansion
    signal_direction: Mapped[str] = mapped_column(
        String(20), nullable=False, default="positive"
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    extra_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
