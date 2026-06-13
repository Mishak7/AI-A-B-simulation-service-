from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExperimentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    conversion_goal: str = Field(..., min_length=1)
    target_audience: str | None = None


class ExperimentRead(BaseModel):
    id: int
    name: str
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
