from pydantic import BaseModel, ConfigDict


class PersonaProfile(BaseModel):
    name: str
    age_range: str
    occupation: str
    income_level: str
    education: str
    location: str
    interests: str
    goals: str
    pain_points: str
    technical_savviness: str
    online_behavior: str
    browsing_context: str
    task_context: str


class PersonaRead(PersonaProfile):
    id: int
    experiment_id: int

    model_config = ConfigDict(from_attributes=True)
