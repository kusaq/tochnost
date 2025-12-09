from sqlalchemy import String, BigInteger, Float, Boolean, text
from sqlalchemy.orm import Mapped, mapped_column

from infra.timescale_db.models.base import Base
from infra.timescale_db.mixins import CreateAndUpdateTimestampMixin


class Threshold(Base, CreateAndUpdateTimestampMixin):
    __tablename__ = "threshold"

    threshold_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    min_value: Mapped[float] = mapped_column(Float, nullable=False)
    max_value: Mapped[float] = mapped_column(Float, nullable=False)
    unit_of_measurement: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
