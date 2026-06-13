from sqlalchemy import Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ExperimentReport(Base):
    __tablename__ = "experiment_reports"

    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), primary_key=True)
    control_votes: Mapped[int] = mapped_column(Integer)
    challenger_votes: Mapped[int] = mapped_column(Integer)
    none_votes: Mapped[int] = mapped_column(Integer)
    winner: Mapped[str] = mapped_column(Text)
    confidence_score: Mapped[float] = mapped_column(Float)
    image_1_visual_fail_rate: Mapped[float] = mapped_column(Float, default=0.0)
    image_2_visual_fail_rate: Mapped[float] = mapped_column(Float, default=0.0)
    control_visual_fail_rate: Mapped[float] = mapped_column(Float, default=0.0)
    challenger_visual_fail_rate: Mapped[float] = mapped_column(Float, default=0.0)
    top_control_reasons: Mapped[str] = mapped_column(Text)
    top_challenger_reasons: Mapped[str] = mapped_column(Text)
    top_none_reasons: Mapped[str] = mapped_column(Text)
    recommendations: Mapped[str] = mapped_column(Text)
    limitations: Mapped[str] = mapped_column(Text)

    experiment = relationship("Experiment", back_populates="report")
