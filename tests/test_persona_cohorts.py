import asyncio
from collections import Counter

import pytest
from pydantic import ValidationError

from app.llm.mock_client import MockLLMClient
from app.schemas.persona import ALLOWED_COHORTS, PersonaProfile
from app.services.prompt_renderer import PromptRenderer


COHORT_FIELDS = {
    "cohort",
    "cohort_motivation",
    "information_discovery_style",
    "typical_behavior",
    "funnel_exit_risk",
}


@pytest.mark.parametrize("requested_count", [3, 5, 12])
def test_mock_personas_include_balanced_allowed_cohorts_and_requested_count(
    requested_count: int,
) -> None:
    personas = asyncio.run(
        MockLLMClient().generate_personas("Existing personas: None", requested_count)
    )

    assert len(personas) == requested_count
    assert all(COHORT_FIELDS <= persona.model_dump().keys() for persona in personas)
    assert all(persona.cohort in ALLOWED_COHORTS for persona in personas)

    cohort_counts = Counter(persona.cohort for persona in personas)
    assert len(cohort_counts) == min(requested_count, len(ALLOWED_COHORTS))
    assert max(cohort_counts.values()) - min(cohort_counts.values()) <= 1


def test_persona_schema_rejects_unknown_cohort() -> None:
    persona = asyncio.run(MockLLMClient().generate_personas("", 1))[0]

    with pytest.raises(ValidationError):
        PersonaProfile.model_validate(
            {**persona.model_dump(), "cohort": "Новая придуманная когорта"}
        )


def test_persona_generation_prompt_documents_cohort_contract() -> None:
    rendered = PromptRenderer().render(
        "persona_generation.md",
        {
            "conversion_goal": "Submit application",
            "target_audience": "Retail banking customers",
            "num_personas": 5,
            "existing_personas": [],
            "image_1_description": "Screenshot",
            "image_2_description": "Screenshot",
            "experiment_context": {},
        },
    )

    assert all(field in rendered for field in COHORT_FIELDS)
    assert all(cohort in rendered for cohort in ALLOWED_COHORTS)
    assert "exactly\n5 persona objects" in rendered
    assert "as evenly as mathematically possible" in rendered
