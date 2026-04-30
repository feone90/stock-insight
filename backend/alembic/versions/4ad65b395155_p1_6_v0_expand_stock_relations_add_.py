"""p1.6 v0 expand stock_relations + add relation_candidates

Revision ID: 4ad65b395155
Revises: d775cc639fe7
Create Date: 2026-04-30 10:10:12.785409

Spec: docs/superpowers/specs/2026-04-30-ontology-architecture.md §4
Plan: docs/superpowers/plans/2026-04-30-p1.6-relation-extraction.md §5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '4ad65b395155'
down_revision: Union[str, None] = 'd775cc639fe7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_RELATION_TYPES = (
    "peer", "supply_upstream", "supply_downstream", "group", "theme", "macro",
    "competitor", "contract_supplier", "contract_customer",
    "complementary", "regulatory_link",
)


def upgrade() -> None:
    """P1.6 v0 — stock_relations expansion + relation_candidates buffer."""
    # 1. stock_relations 컬럼 추가
    op.add_column(
        "stock_relations",
        sa.Column(
            "signal_direction",
            sa.String(20),
            nullable=False,
            server_default="positive",
        ),
    )
    op.add_column(
        "stock_relations",
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
    )
    op.add_column("stock_relations", sa.Column("valid_from", sa.Date(), nullable=True))
    op.add_column("stock_relations", sa.Column("valid_until", sa.Date(), nullable=True))
    op.add_column(
        "stock_relations",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "stock_relations",
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
    )

    # 2. relation_type CHECK — 11 type 허용
    in_clause = ", ".join(f"'{t}'" for t in _RELATION_TYPES)
    op.execute(
        "ALTER TABLE stock_relations "
        "DROP CONSTRAINT IF EXISTS stock_relations_relation_type_check"
    )
    op.execute(
        f"ALTER TABLE stock_relations "
        f"ADD CONSTRAINT stock_relations_relation_type_check "
        f"CHECK (relation_type IN ({in_clause}))"
    )

    # 3. composite index for signal-direction-aware top-N queries
    op.create_index(
        "ix_relations_from_signal_score",
        "stock_relations",
        ["from_stock_id", "signal_direction"],
    )

    # 4. relation_candidates 테이블 (Tier 3 buffer)
    op.create_table(
        "relation_candidates",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("from_ticker", sa.String(20), nullable=False),
        sa.Column("to_ticker", sa.String(20), nullable=False),
        sa.Column("relation_type", sa.String(30), nullable=False),
        sa.Column(
            "signal_direction", sa.String(20), nullable=False, server_default="positive"
        ),
        sa.Column("strength", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "extracted_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("promoted_at", sa.DateTime(), nullable=True),
        sa.Column(
            "promoted_to_relation_id",
            sa.BigInteger(),
            sa.ForeignKey("stock_relations.id"),
            nullable=True,
        ),
    )

    # 5. relation_candidates indexes
    op.create_index(
        "ix_candidates_pending",
        "relation_candidates",
        ["promoted_at"],
        postgresql_where=sa.text("promoted_at IS NULL"),
    )
    op.create_index("ix_candidates_from_ticker", "relation_candidates", ["from_ticker"])
    op.create_index("ix_candidates_to_ticker", "relation_candidates", ["to_ticker"])


def downgrade() -> None:
    """Revert P1.6 v0."""
    op.drop_index("ix_candidates_to_ticker", table_name="relation_candidates")
    op.drop_index("ix_candidates_from_ticker", table_name="relation_candidates")
    op.drop_index("ix_candidates_pending", table_name="relation_candidates")
    op.drop_table("relation_candidates")

    op.drop_index("ix_relations_from_signal_score", table_name="stock_relations")
    op.execute(
        "ALTER TABLE stock_relations "
        "DROP CONSTRAINT IF EXISTS stock_relations_relation_type_check"
    )
    op.drop_column("stock_relations", "metadata")
    op.drop_column("stock_relations", "is_active")
    op.drop_column("stock_relations", "valid_until")
    op.drop_column("stock_relations", "valid_from")
    op.drop_column("stock_relations", "confidence")
    op.drop_column("stock_relations", "signal_direction")
