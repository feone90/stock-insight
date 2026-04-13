"""add analysis unique constraint

Revision ID: a1b2c3d4e5f6
Revises: 3785bdda88c3
Create Date: 2026-04-13 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "3785bdda88c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_analysis_stock_date_period",
        "analyses",
        ["stock_id", "date", "period_type"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_analysis_stock_date_period", "analyses", type_="unique")
