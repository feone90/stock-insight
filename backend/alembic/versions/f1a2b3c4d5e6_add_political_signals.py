"""add political_signals + political_signal_tickers

Revision ID: f1a2b3c4d5e6
Revises: 4ad65b395155
Create Date: 2026-05-12 11:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "4ad65b395155"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "political_signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_post_id", sa.String(128), nullable=False),
        sa.Column("author", sa.String(64), nullable=False),
        sa.Column("posted_at", sa.DateTime(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_lang", sa.String(8), nullable=False, server_default="en"),
        sa.Column("url", sa.String(512), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(), nullable=True),
        sa.Column("is_market_relevant", sa.Boolean(), nullable=True),
        sa.Column("summary_ko", sa.Text(), nullable=True),
        sa.Column("overall_sentiment", sa.String(16), nullable=True),
        sa.Column("macro_themes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("analyzer_version", sa.String(32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_political_signals_posted_at",
        "political_signals",
        ["posted_at"],
    )
    op.create_index(
        "ix_political_signals_source_post",
        "political_signals",
        ["source", "source_post_id"],
        unique=True,
    )

    op.create_table(
        "political_signal_tickers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "signal_id",
            sa.Integer(),
            sa.ForeignKey("political_signals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("sentiment", sa.String(16), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("strength", sa.String(8), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("expected_window", sa.String(16), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("sector_impact", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "signal_id",
            "ticker",
            name="uq_political_signal_ticker",
        ),
    )
    op.create_index(
        "ix_political_signal_tickers_ticker",
        "political_signal_tickers",
        ["ticker"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_political_signal_tickers_ticker",
        table_name="political_signal_tickers",
    )
    op.drop_table("political_signal_tickers")
    op.drop_index(
        "ix_political_signals_source_post",
        table_name="political_signals",
    )
    op.drop_index(
        "ix_political_signals_posted_at",
        table_name="political_signals",
    )
    op.drop_table("political_signals")
