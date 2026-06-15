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
    financial_literacy: str
    digital_literacy: str
    trust_in_online_banking: str
    fraud_anxiety: str
    fee_sensitivity: str
    privacy_sensitivity: str
    banking_channel_preference: str
    decision_style: str
    region_type: str
    income_stability: str
    online_behavior: str
    browsing_context: str
    task_context: str


class PersonaRead(PersonaProfile):
    id: int
    experiment_id: int

    model_config = ConfigDict(from_attributes=True)
