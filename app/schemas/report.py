from pydantic import BaseModel, ConfigDict


from app.schemas.simulation import SimulationResultRead


class ExperimentReportRead(BaseModel):
    experiment_id: int
    control_votes: int
    challenger_votes: int
    none_votes: int
    winner: str
    confidence_score: float
    image_1_visual_fail_rate: float
    image_2_visual_fail_rate: float
    control_visual_fail_rate: float
    challenger_visual_fail_rate: float
    image_1_votes: int = 0
    image_2_votes: int = 0
    position_switch_rate: float = 0.0
    positional_bias_score: float = 0.0
    top_control_reasons: list[str]
    top_challenger_reasons: list[str]
    top_none_reasons: list[str]
    recommendations: list[str]
    limitations: str
    agent_results: list[SimulationResultRead] = []

    model_config = ConfigDict(from_attributes=True)
