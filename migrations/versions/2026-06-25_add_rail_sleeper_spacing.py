"""add rail sleeper_spacing_mm (эпюра — среднее расстояние между шпалами)

Revision ID: e5b2c7a14f03
Revises: d4a1e8f93b02
Create Date: 2026-06-25

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5b2c7a14f03"
down_revision: Union[str, Sequence[str], None] = "d4a1e8f93b02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rail",
        sa.Column(
            "sleeper_spacing_mm",
            sa.Integer(),
            nullable=True,
            comment="Среднее расстояние между шпалами (эпюра), мм",
        ),
    )


def downgrade() -> None:
    op.drop_column("rail", "sleeper_spacing_mm")
