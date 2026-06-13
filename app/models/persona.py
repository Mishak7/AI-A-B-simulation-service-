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
    online_behavior: Mapped[str] = mapped_column(Text)
    browsing_context: Mapped[str] = mapped_column(Text)
    task_context: Mapped[str] = mapped_column(Text)

    experiment = relationship("Experiment", back_populates="personas")
    simulation_results = relationship(
        "SimulationResult", back_populates="persona", cascade="all, delete-orphan"
    )
