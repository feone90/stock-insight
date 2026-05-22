from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.stock import Base


class DailyPriceDriver(Base):
    """Finalized next-day explanation for one completed trading day.

    Rows are intentionally immutable by default: once yesterday's driver is
    extracted, card refreshes must read this row instead of spending LLM cost
    again. Admin backfill can force replacement for recovery/debugging.
    """

    __tablename__ = "daily_price_drivers"
    __table_args__ = (
        UniqueConstraint(
            "stock_id",
            "trade_date",
            "model_version",
            name="uq_daily_price_driver_stock_date_model",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False, default="neutral")
    keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
