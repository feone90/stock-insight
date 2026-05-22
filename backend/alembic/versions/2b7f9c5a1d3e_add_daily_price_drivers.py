"""add daily price drivers

Revision ID: 2b7f9c5a1d3e
Revises: 1c31615e8536
Create Date: 2026-05-22 10:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "2b7f9c5a1d3e"
down_revision: Union[str, None] = "1c31615e8536"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_price_drivers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("keywords", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "stock_id",
            "trade_date",
            "model_version",
            name="uq_daily_price_driver_stock_date_model",
        ),
    )
    op.create_index(
        "ix_daily_price_drivers_stock_date",
        "daily_price_drivers",
        ["stock_id", "trade_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_daily_price_drivers_stock_date", table_name="daily_price_drivers")
    op.drop_table("daily_price_drivers")
