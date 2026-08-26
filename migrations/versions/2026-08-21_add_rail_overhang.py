"""add rail overhang (забег нитей) + позиции торцов в sensor_1

Revision ID: f1a6d09c3b27
Revises: e5b2c7a14f03
Create Date: 2026-08-21

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a6d09c3b27"
down_revision: Union[str, Sequence[str], None] = "e5b2c7a14f03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SENSOR1_COLUMNS = [
    ("mmRailStartLeft", "позиция начала левого рельса в мм (для забега)"),
    ("mmRailStartRight", "позиция начала правого рельса в мм (для забега)"),
    ("mmRailEndLeft", "позиция конца левого рельса в мм (для забега)"),
    ("mmRailEndRight", "позиция конца правого рельса в мм (для забега)"),
]


def upgrade() -> None:
    for name, comment in SENSOR1_COLUMNS:
        op.add_column("sensor_1", sa.Column(name, sa.BigInteger(), nullable=True, comment=comment))

    op.add_column(
        "rail",
        sa.Column("overhang_start_mm", sa.Integer(), nullable=True, comment="Забег в начале РШР (левая нить − правая), мм"),
    )
    op.add_column(
        "rail",
        sa.Column("overhang_end_mm", sa.Integer(), nullable=True, comment="Забег в конце РШР (левая нить − правая), мм"),
    )

    # Дефолтный допуск ±50 мм. Консервативно: ловим только грубые дефекты, пока
    # не накопится статистика реального разброса. Правится UPDATE-ом без деплоя.
    # is_critical=false — метрика новая, не хотим сразу красить РШР в критику.
    op.execute(
        """
        INSERT INTO threshold (value, min_value, max_value, unit_of_measurement, is_critical)
        SELECT 'mm_overhang', -50, 50, 'мм', false
        WHERE NOT EXISTS (SELECT 1 FROM threshold WHERE value = 'mm_overhang')
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM threshold WHERE value = 'mm_overhang'")
    op.drop_column("rail", "overhang_end_mm")
    op.drop_column("rail", "overhang_start_mm")
    for name, _ in reversed(SENSOR1_COLUMNS):
        op.drop_column("sensor_1", name)
