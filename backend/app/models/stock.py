from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Numeric,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Stock(Base):
    """Stock with universe tier classification (P1.7).

    `tier` semantics:
      1 = Reference Universe core (KOSPI 200 / KOSDAQ 200 / S&P 500 +
          GICS sector quota). ontology cross-match operates on tier 1+2.
      2 = User-touched (favorite, card view). Auto-promoted from tier 3.
      3 = Latent (metadata only, ontology cross-match skipped).
    """

    __tablename__ = "stocks"
    __table_args__ = (
        Index("ix_stocks_tier", "tier"),
        Index("ix_stocks_sector_tier", "sector", "tier"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    market: Mapped[str] = mapped_column(String(20))
    sector: Mapped[str] = mapped_column(String(100))
    current_price: Mapped[float] = mapped_column(Float, default=0)
    change: Mapped[float] = mapped_column(Float, default=0)
    change_percent: Mapped[float] = mapped_column(Float, default=0)
    dart_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # P1.7 universe tier columns
    tier: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3)
    industry_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    avg_volume_30d: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    is_delisted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tier_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    universe_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
