from datetime import datetime

from sqlalchemy import Date, DateTime, Float, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.stock import Base


class MacroFactor(Base):
    """Daily snapshot of one macro factor (e.g. VIX, US10Y, USD/KRW)."""

    __tablename__ = "macro_factors"
    __table_args__ = (
        UniqueConstraint("factor", "date", name="uq_macro_factor_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    factor: Mapped[str] = mapped_column(String(40))  # "VIX", "US10Y", "USD/KRW", "XLK", etc.
    date: Mapped[str] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(40), default="market_data")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
