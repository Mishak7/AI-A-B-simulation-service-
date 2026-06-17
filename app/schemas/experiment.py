from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.experiment import ExperimentMode


class ExperimentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    mode: ExperimentMode = ExperimentMode.ab_test
    conversion_goal: str = ""
    target_audience: str | None = None


class ExperimentRead(BaseModel):
    id: int
    name: str
    mode: str
    conversion_goal: str
    target_audience: str | None
    control_image_path: str | None
    challenger_image_path: str | None
    status: str
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class RunExperimentRequest(BaseModel):
    num_personas: int = Field(default=50, ge=1, le=500)
    batch_size: int = Field(default=10, ge=1, le=50)
    early_stopping: bool = False


class RunVariantGenerationRequest(BaseModel):
    batch_size: int = Field(default=10, ge=1, le=50)
