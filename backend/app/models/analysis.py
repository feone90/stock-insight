from datetime import datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.stock import Base


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        UniqueConstraint("stock_id", "date", "period_type", name="uq_analysis_stock_date_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    date: Mapped[str] = mapped_column(Date)
    period_type: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(Text)
    feedback: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # v2 additions — nullable for Phase A backwards compat.
    schema_version: Mapped[str] = mapped_column(String(10), nullable=False, server_default="v1")
    card_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    persona_version: Mapped[str | None] = mapped_column(String(40), nullable=True)

    keywords: Mapped[list["KeywordDetail"]] = relationship(back_populates="analysis", cascade="all, delete-orphan")
    daily_keywords: Mapped[list["DailyKeyword"]] = relationship(back_populates="analysis", cascade="all, delete-orphan")


class KeywordDetail(Base):
    __tablename__ = "keyword_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"))
    keyword: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(200))
    impact_level: Mapped[str] = mapped_column(String(20))
    duration: Mapped[str] = mapped_column(String(20))

    analysis: Mapped["Analysis"] = relationship(back_populates="keywords")


class DailyKeyword(Base):
    __tablename__ = "daily_keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"))
    date: Mapped[str] = mapped_column(Date)
    keyword: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20))

    analysis: Mapped["Analysis"] = relationship(back_populates="daily_keywords")
