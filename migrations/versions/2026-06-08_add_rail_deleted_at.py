"""add rail deleted_at for soft delete

Revision ID: d4a1e8f93b02
Revises: c8f3b2d41e05
Create Date: 2026-06-08

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4a1e8f93b02"
down_revision: Union[str, Sequence[str], None] = "c8f3b2d41e05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rail",
        sa.Column(
            "deleted_at",
            sa.DateTime(),
            nullable=True,
            comment="Метка мягкого удаления; NULL — запись активна",
        ),
    )
    op.create_index("ix_rail_deleted_at", "rail", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_rail_deleted_at", table_name="rail")
    op.drop_column("rail", "deleted_at")
