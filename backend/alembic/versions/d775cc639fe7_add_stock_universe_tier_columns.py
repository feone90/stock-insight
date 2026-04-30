"""add stock universe tier columns

Revision ID: d775cc639fe7
Revises: a68d8f268caf
Create Date: 2026-04-30 08:25:04.200789

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd775cc639fe7'
down_revision: Union[str, None] = 'a68d8f268caf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add P1.7 universe tier columns + indexes.

    Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §3.1
    Plan: docs/superpowers/plans/2026-04-30-p1.7-reference-universe.md §5
    """
    op.add_column(
        "stocks",
        sa.Column("tier", sa.SmallInteger(), nullable=False, server_default="3"),
    )
    op.add_column("stocks", sa.Column("industry_group", sa.String(100), nullable=True))
    op.add_column("stocks", sa.Column("market_cap", sa.Numeric(18, 2), nullable=True))
    op.add_column("stocks", sa.Column("avg_volume_30d", sa.Numeric(18, 2), nullable=True))
    op.add_column(
        "stocks",
        sa.Column("is_delisted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("stocks", sa.Column("tier_updated_at", sa.DateTime(), nullable=True))
    op.add_column("stocks", sa.Column("universe_source", sa.String(50), nullable=True))

    op.create_index("ix_stocks_tier", "stocks", ["tier"])
    op.create_index("ix_stocks_sector_tier", "stocks", ["sector", "tier"])

    # Existing seed (005930, TSLA, etc.) treated as tier=2 (user-touched).
    # The first run of `seed_universe.py` will promote them to tier=1 if they
    # qualify for the reference core; otherwise they stay tier=2.
    op.execute(
        "UPDATE stocks SET tier = 2, universe_source = 'seed_legacy' "
        "WHERE tier = 3"
    )


def downgrade() -> None:
    """Revert P1.7 universe tier columns."""
    op.drop_index("ix_stocks_sector_tier", table_name="stocks")
    op.drop_index("ix_stocks_tier", table_name="stocks")
    op.drop_column("stocks", "universe_source")
    op.drop_column("stocks", "tier_updated_at")
    op.drop_column("stocks", "is_delisted")
    op.drop_column("stocks", "avg_volume_30d")
    op.drop_column("stocks", "market_cap")
    op.drop_column("stocks", "industry_group")
    op.drop_column("stocks", "tier")
