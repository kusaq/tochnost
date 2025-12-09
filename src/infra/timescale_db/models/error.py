from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from infra.timescale_db.mixins import CreateAndUpdateTimestampMixin
from infra.timescale_db.models.base import Base


class Error(Base, CreateAndUpdateTimestampMixin):
    __tablename__ = "error"

    error_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    rail_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("rail.rail_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        comment="идентификатор рельса",
    )
    screw_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("screw.screw_id", onupdate="CASCADE", ondelete="CASCADE",),
        nullable=True,
        comment="идентификатор гайки",
    )

    value_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit_of_measurement: Mapped[str | None] = mapped_column(String(255), nullable=True)
    value: Mapped[str] = mapped_column(Float, nullable=False)
    min_value: Mapped[float] = mapped_column(Float, nullable=False)
    max_value: Mapped[float] = mapped_column(Float, nullable=False)
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_fixed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
