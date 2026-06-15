import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMClient
from app.models import Experiment, Persona
from app.schemas.persona import PersonaProfile
from app.services.prompt_renderer import PromptRenderer

logger = logging.getLogger(__name__)


class PersonaGenerator:
    def __init__(self, llm_client: LLMClient, prompt_renderer: PromptRenderer) -> None:
        self.llm_client = llm_client
        self.prompt_renderer = prompt_renderer

    async def generate(
        self,
        session: AsyncSession,
        experiment: Experiment,
        num_personas: int,
        batch_size: int,
    ) -> list[Persona]:
        created: list[Persona] = []
        existing_personas: list[dict[str, str]] = []

        for start in range(0, num_personas, batch_size):
            current_batch_size = min(batch_size, num_personas - start)
            batch_number = (start // batch_size) + 1
            logger.info(
                "Generating persona batch experiment_id=%s batch=%s requested=%s already_created=%s",
                experiment.id,
                batch_number,
                current_batch_size,
                len(created),
            )
            context = {
                "conversion_goal": experiment.conversion_goal,
                "target_audience": experiment.target_audience,
                "num_personas": current_batch_size,
                "existing_personas": existing_personas,
                "image_1_description": "Local uploaded interface screenshot.",
                "image_2_description": "Local uploaded interface screenshot.",
                "experiment_context": {
                    "experiment_id": experiment.id,
                    "experiment_name": experiment.name,
                },
            }
            profiles = await self._generate_batch(context, current_batch_size)
            logger.info(
                "Persona batch generated experiment_id=%s batch=%s returned=%s",
                experiment.id,
                batch_number,
                len(profiles),
            )

            for profile in profiles:
                persona = Persona(experiment_id=experiment.id, **profile.model_dump())
                session.add(persona)
                created.append(persona)
                existing_personas.append({"name": profile.name, "occupation": profile.occupation})
                logger.info(
                    "Generated persona experiment_id=%s name=%r age=%s occupation=%r income=%r "
                    "location=%r financial_literacy=%r digital_literacy=%r trust_online=%r "
                    "fraud_anxiety=%r fee_sensitivity=%r privacy_sensitivity=%r channel=%r "
                    "decision_style=%r region_type=%r income_stability=%r",
                    experiment.id,
                    profile.name,
                    profile.age_range,
                    profile.occupation,
                    profile.income_level,
                    profile.location,
                    profile.financial_literacy,
                    profile.digital_literacy,
                    profile.trust_in_online_banking,
                    profile.fraud_anxiety,
                    profile.fee_sensitivity,
                    profile.privacy_sensitivity,
                    profile.banking_channel_preference,
                    profile.decision_style,
                    profile.region_type,
                    profile.income_stability,
                )

            await session.flush()

        return created

    async def _generate_batch(
        self,
        context: dict,
        target_count: int,
        max_attempts: int = 3,
    ) -> list[PersonaProfile]:
        profiles: list[PersonaProfile] = []

        for _ in range(max_attempts):
            remaining = target_count - len(profiles)
            if remaining <= 0:
                break

            retry_context = {
                **context,
                "num_personas": remaining,
                "existing_personas": [
                    *context["existing_personas"],
                    *[
                        {"name": profile.name, "occupation": profile.occupation}
                        for profile in profiles
                    ],
                ],
            }
            logger.info(
                "Persona generation attempt target=%s current=%s remaining=%s",
                target_count,
                len(profiles),
                remaining,
            )
            prompt = self.prompt_renderer.render("persona_generation.md", retry_context)
            new_profiles = await self.llm_client.generate_personas(prompt, remaining)
            profiles.extend(new_profiles)
            logger.info(
                "Persona generation attempt returned=%s total=%s target=%s",
                len(new_profiles),
                len(profiles),
                target_count,
            )

        if len(profiles) < target_count:
            logger.error("Persona generation exhausted retries expected=%s got=%s", target_count, len(profiles))
            raise ValueError(f"Expected {target_count} personas, got {len(profiles)} after retries")
        return profiles[:target_count]
