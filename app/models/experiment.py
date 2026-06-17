from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ExperimentStatus(StrEnum):
    created = "created"
    running = "running"
    completed = "completed"
    failed = "failed"


class ExperimentMode(StrEnum):
    ab_test = "ab_test"
    variant_generation = "variant_generation"


class Experiment(Base, TimestampMixin):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    mode: Mapped[ExperimentMode] = mapped_column(
        Enum(ExperimentMode), default=ExperimentMode.ab_test
    )
    conversion_goal: Mapped[str] = mapped_column(Text)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    control_image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    challenger_image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[ExperimentStatus] = mapped_column(
        Enum(ExperimentStatus), default=ExperimentStatus.created
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    personas = relationship("Persona", back_populates="experiment", cascade="all, delete-orphan")
    simulation_results = relationship(
        "SimulationResult", back_populates="experiment", cascade="all, delete-orphan"
    )
    report = relationship(
        "ExperimentReport", back_populates="experiment", cascade="all, delete-orphan", uselist=False
    )
