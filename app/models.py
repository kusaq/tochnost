from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class CaptureSession(Base):
    __tablename__ = "capture_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uid: Mapped[str] = mapped_column(String(128), nullable=False)
    connection_class: Mapped[str] = mapped_column(String(128), nullable=False)
    front_saved: Mapped[int] = mapped_column(Integer, default=0)
    top_saved: Mapped[int] = mapped_column(Integer, default=0)
    front_dir: Mapped[str] = mapped_column(Text, nullable=False)
    top_dir: Mapped[str] = mapped_column(Text, nullable=False)
    front_archive: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    top_archive: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    errors: Mapped[List[str]] = mapped_column(JSON, default=list)
    camera_config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Связь с решеткой
    rail_grid_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rail_grids.id"), nullable=True, index=True
    )
    rail_grid: Mapped[Optional["RailGrid"]] = relationship(
        "RailGrid", back_populates="capture_sessions"
    )


class RailGrid(Base):
    """Модель рельсошпальной решетки."""
    __tablename__ = "rail_grids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uuid: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, index=True,
        default=lambda: str(uuid.uuid4())
    )
    connection_class: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False
    )  # active, completed
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    extra: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Связь с показаниями Modbus
    modbus_readings: Mapped[List["ModbusReading"]] = relationship(
        "ModbusReading", back_populates="rail_grid", cascade="all, delete-orphan"
    )
    # Связь с сессиями фотографирования
    capture_sessions: Mapped[List["CaptureSession"]] = relationship(
        "CaptureSession", back_populates="rail_grid"
    )


class ModbusReading(Base):
    __tablename__ = "modbus_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    values: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    extra: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    # Связь с решеткой
    rail_grid_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rail_grids.id"), nullable=True, index=True
    )
    rail_grid: Mapped[Optional["RailGrid"]] = relationship(
        "RailGrid", back_populates="modbus_readings"
    )


