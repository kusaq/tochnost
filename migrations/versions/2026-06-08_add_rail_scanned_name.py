"""add rail scanned_name

Revision ID: c8f3b2d41e05
Revises: b7e4a1c92d10
Create Date: 2026-06-08

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8f3b2d41e05"
down_revision: Union[str, Sequence[str], None] = "b7e4a1c92d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rail",
        sa.Column(
            "scanned_name",
            sa.String(255),
            nullable=True,
            comment="Считанный номер РШР (OCR/нейросеть)",
        ),
    )


def downgrade() -> None:
    op.drop_column("rail", "scanned_name")
