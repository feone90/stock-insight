from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.stock import Base


class StockRelation(Base):
    """An ontology edge: from_stock --[type]--> to_target.

    `to_target` may be a Stock (FK by ticker stored as string) OR a virtual node
    (theme/macro factor). Hence string column not FK — virtual nodes don't have
    a row in `stocks`.
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
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    to_target: Mapped[str] = mapped_column(String(100))  # ticker OR theme name OR factor name
    to_kind: Mapped[str] = mapped_column(String(20))  # "stock" | "theme" | "macro"
    relation_type: Mapped[str] = mapped_column(String(30))
    # peer | supply_upstream | supply_downstream | group | theme | macro

    strength: Mapped[float] = mapped_column(Float, default=0.5)  # 0..1
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="llm-curation")
    discovered_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
