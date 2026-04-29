"""add source to stock_relations unique

Revision ID: a68d8f268caf
Revises: a3f4ec76d96d
Create Date: 2026-04-29 14:07:00.678702

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a68d8f268caf'
down_revision: Union[str, None] = 'a3f4ec76d96d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add `source` to the unique tuple so two writers (auto sector_match
    post-save hook and llm_web_search bg refresh) can persist the same
    (from, to, type) edge in parallel rows without conflicting.

    Per spec §9 — Concurrent writer 처리.
    """
    op.drop_constraint("uq_relation_triple", "stock_relations", type_="unique")
    op.create_unique_constraint(
        "uq_relation_triple",
        "stock_relations",
        ["from_stock_id", "to_target", "relation_type", "source"],
    )


def downgrade() -> None:
    """Revert to the 3-tuple unique."""
    op.drop_constraint("uq_relation_triple", "stock_relations", type_="unique")
    op.create_unique_constraint(
        "uq_relation_triple",
        "stock_relations",
        ["from_stock_id", "to_target", "relation_type"],
    )
