"""add user_id to favorites

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-13 13:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. user_id 컬럼 추가 (기본값 'default'로 기존 행 처리)
    op.add_column("favorites", sa.Column("user_id", sa.String(200), nullable=False, server_default="default"))
    # 2. 기존 unique constraint 삭제
    op.drop_constraint("uq_favorite_stock", "favorites", type_="unique")
    # 3. 새 unique constraint 추가 (user_id, stock_id)
    op.create_unique_constraint("uq_favorite_user_stock", "favorites", ["user_id", "stock_id"])


def downgrade() -> None:
    op.drop_constraint("uq_favorite_user_stock", "favorites", type_="unique")
    op.drop_column("favorites", "user_id")
    op.create_unique_constraint("uq_favorite_stock", "favorites", ["stock_id"])
