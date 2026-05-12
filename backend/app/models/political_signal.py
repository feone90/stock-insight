"""정치/매크로 발언 (트럼프 Truth Social 등) — 시장 영향 분석 source.

미래 자동매매 trigger 가능한 schema:
  - PoliticalSignal: 원본 게시물 + LLM 분석 cache (idempotent dedup)
  - PoliticalSignalTicker: 영향 종목 1:N — direction/strength/window가
    매수/매도 action 매핑 기반 (long/short/avoid, urgency)
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.stock import Base


class PoliticalSignal(Base):
    """정치/매크로 발언 단위. 카드 뉴스/이슈에 highlight 노출."""

    __tablename__ = "political_signals"
    __table_args__ = (
        Index("ix_political_signals_posted_at", "posted_at"),
        Index(
            "ix_political_signals_source_post",
            "source",
            "source_post_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))  # "truth_social"
    source_post_id: Mapped[str] = mapped_column(String(128))  # dedup
    author: Mapped[str] = mapped_column(String(64))  # "realDonaldTrump"
    posted_at: Mapped[datetime] = mapped_column(DateTime)
    content: Mapped[str] = mapped_column(Text)
    content_lang: Mapped[str] = mapped_column(String(8), default="en")
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # LLM 분석 cache — analyzed_at 있으면 재호출 X
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_market_relevant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    summary_ko: Mapped[str | None] = mapped_column(Text, nullable=True)
    overall_sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    macro_themes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    analyzer_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    tickers: Mapped[list["PoliticalSignalTicker"]] = relationship(
        back_populates="signal",
        cascade="all, delete-orphan",
    )


class PoliticalSignalTicker(Base):
    """signal → 영향 종목 1:N. 미래 자동매매 trigger row.

    direction / expected_window / confidence 셋이 매매 action 매핑 기준:
      - direction=long + strength=high + window=hours → 즉시 매수 candidate
      - direction=short → 매도 / 회피
      - confidence<0.5 → 자동 매매 제외 (관찰만)
    """

    __tablename__ = "political_signal_tickers"
    __table_args__ = (
        UniqueConstraint("signal_id", "ticker", name="uq_political_signal_ticker"),
        Index("ix_political_signal_tickers_ticker", "ticker"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[int] = mapped_column(
        ForeignKey("political_signals.id", ondelete="CASCADE")
    )
    ticker: Mapped[str] = mapped_column(String(20))

    sentiment: Mapped[str] = mapped_column(String(16))  # bullish / bearish / neutral
    direction: Mapped[str] = mapped_column(String(16))  # long / short / avoid
    strength: Mapped[str] = mapped_column(String(8))  # high / medium / low
    confidence: Mapped[float] = mapped_column(Float)  # 0~1
    expected_window: Mapped[str] = mapped_column(String(16))
    # minutes / hours / 1-3days / 1-2weeks

    reasoning: Mapped[str] = mapped_column(Text)
    sector_impact: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    signal: Mapped[PoliticalSignal] = relationship(back_populates="tickers")
