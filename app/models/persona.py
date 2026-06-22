from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    age_range: Mapped[str] = mapped_column(String(64))
    occupation: Mapped[str] = mapped_column(String(255))
    income_level: Mapped[str] = mapped_column(String(128))
    education: Mapped[str] = mapped_column(String(255))
    location: Mapped[str] = mapped_column(String(255))
    interests: Mapped[str] = mapped_column(Text)
    goals: Mapped[str] = mapped_column(Text)
    pain_points: Mapped[str] = mapped_column(Text)
    technical_savviness: Mapped[str] = mapped_column(String(128))
    financial_literacy: Mapped[str] = mapped_column(String(128))
    digital_literacy: Mapped[str] = mapped_column(String(128))
    trust_in_online_banking: Mapped[str] = mapped_column(String(128))
    fraud_anxiety: Mapped[str] = mapped_column(String(128))
    fee_sensitivity: Mapped[str] = mapped_column(String(128))
    privacy_sensitivity: Mapped[str] = mapped_column(String(128))
    banking_channel_preference: Mapped[str] = mapped_column(String(255))
    decision_style: Mapped[str] = mapped_column(String(255))
    region_type: Mapped[str] = mapped_column(String(128))
    income_stability: Mapped[str] = mapped_column(String(128))
    online_behavior: Mapped[str] = mapped_column(Text)
    browsing_context: Mapped[str] = mapped_column(Text)
    task_context: Mapped[str] = mapped_column(Text)
    cohort: Mapped[str] = mapped_column(String(64))
    cohort_motivation: Mapped[str] = mapped_column(Text)
    information_discovery_style: Mapped[str] = mapped_column(Text)
    typical_behavior: Mapped[str] = mapped_column(Text)
    funnel_exit_risk: Mapped[str] = mapped_column(Text)

    experiment = relationship("Experiment", back_populates="personas")
    simulation_results = relationship(
        "SimulationResult", back_populates="persona", cascade="all, delete-orphan"
    )
