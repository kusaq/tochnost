"""rshr summary fields on rail and screw

Revision ID: b7e4a1c92d10
Revises: a086187c6377
Create Date: 2026-05-19

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e4a1c92d10"
down_revision: Union[str, Sequence[str], None] = "a086187c6377"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("rail", sa.Column("length_mm", sa.Integer(), nullable=True, comment="Длина РШР, мм"))
    op.add_column("rail", sa.Column("resistance_avg", sa.Float(), nullable=True))
    op.add_column("rail", sa.Column("resistance_min", sa.Float(), nullable=True))
    op.add_column("rail", sa.Column("resistance_max", sa.Float(), nullable=True))
    op.add_column("rail", sa.Column("temperature_avg", sa.Float(), nullable=True))
    op.add_column("screw", sa.Column("mm_along_rail", sa.Integer(), nullable=True))
    op.add_column("screw", sa.Column("channel", sa.Integer(), nullable=True, comment="Канал ПЧ 1–4 (M1–M4)"))
    op.add_column("screw", sa.Column("max_torque", sa.Float(), nullable=True, comment="Макс. момент за цикл, Н·м"))
    op.add_column("screw", sa.Column("max_frequency", sa.Float(), nullable=True, comment="Макс. частота за цикл, Гц"))


def downgrade() -> None:
    op.drop_column("screw", "max_frequency")
    op.drop_column("screw", "max_torque")
    op.drop_column("screw", "channel")
    op.drop_column("screw", "mm_along_rail")
    op.drop_column("rail", "temperature_avg")
    op.drop_column("rail", "resistance_max")
    op.drop_column("rail", "resistance_min")
    op.drop_column("rail", "resistance_avg")
    op.drop_column("rail", "length_mm")
