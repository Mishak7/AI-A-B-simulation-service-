from typing import Literal

from pydantic import BaseModel, ConfigDict


class SimulationVerdict(BaseModel):
    verdict: Literal["image_1", "image_2", "none"]
    confidence: Literal["low", "medium", "high"]
    rationale: str


class VisualAssessment(BaseModel):
    visual_quality: Literal["pass", "minor_issues", "fail"]
    visual_issues: str


class SimulationResultRead(BaseModel):
    id: int
    experiment_id: int
    persona_id: int
    presented_order: str
    raw_verdict: str
    mapped_verdict: str
    confidence: str
    visual_quality_image_1: str
    visual_quality_image_2: str
    visual_issues: str
    critical_visual_defect: bool
    rationale: str
    normalized_rationale: str | None = None

    model_config = ConfigDict(from_attributes=True)
