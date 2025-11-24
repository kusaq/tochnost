from sqlalchemy import String, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infra.timescale_db.models.base import Base


class Rail(Base):
    __tablename__ = "rail"

    rail_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(255), nullable=False)
    object_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fastening_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sleepers: Mapped[str | None] = mapped_column(String(255), nullable=True)

    sensor1_records = relationship("Sensor1", back_populates="rail")
    sensor2_records = relationship("Sensor2", back_populates="rail")


