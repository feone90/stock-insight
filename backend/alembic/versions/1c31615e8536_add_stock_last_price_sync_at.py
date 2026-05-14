"""add stock last_price_sync_at

Revision ID: 1c31615e8536
Revises: c60b0e84e26c
Create Date: 2026-05-15 08:16:37.117988

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c31615e8536'
down_revision: Union[str, None] = 'c60b0e84e26c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add stocks.last_price_sync_at — sync_prices 매 호출 시 utcnow() 박힘."""
    op.add_column(
        "stocks",
        sa.Column("last_price_sync_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("stocks", "last_price_sync_at")
