from enum import StrEnum

from sqlalchemy import Boolean, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class PresentedOrder(StrEnum):
    control_first = "control_first"
    challenger_first = "challenger_first"


class RawVerdict(StrEnum):
    image_1 = "image_1"
    image_2 = "image_2"
    none = "none"


class MappedVerdict(StrEnum):
    control = "control"
    challenger = "challenger"
    none = "none"


class ConfidenceLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class VisualQuality(StrEnum):
    pass_ = "pass"
    minor_issues = "minor_issues"
    fail = "fail"


class SimulationResult(Base, TimestampMixin):
    __tablename__ = "simulation_results"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), index=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("personas.id"), index=True)
    presented_order: Mapped[PresentedOrder] = mapped_column(Enum(PresentedOrder))
    raw_verdict: Mapped[RawVerdict] = mapped_column(Enum(RawVerdict))
    mapped_verdict: Mapped[MappedVerdict] = mapped_column(Enum(MappedVerdict))
    confidence: Mapped[ConfidenceLevel] = mapped_column(Enum(ConfidenceLevel))
    visual_quality_image_1: Mapped[VisualQuality] = mapped_column(
        Enum(VisualQuality, values_callable=lambda enum: [item.value for item in enum]),
        default=VisualQuality.pass_,
    )
    visual_quality_image_2: Mapped[VisualQuality] = mapped_column(
        Enum(VisualQuality, values_callable=lambda enum: [item.value for item in enum]),
        default=VisualQuality.pass_,
    )
    visual_issues: Mapped[str] = mapped_column(Text, default="")
    critical_visual_defect: Mapped[bool] = mapped_column(Boolean, default=False)
    rationale: Mapped[str] = mapped_column(Text)

    experiment = relationship("Experiment", back_populates="simulation_results")
    persona = relationship("Persona", back_populates="simulation_results")
