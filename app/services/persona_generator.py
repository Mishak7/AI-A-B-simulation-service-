from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMClient
from app.models import Experiment, Persona
from app.schemas.persona import PersonaProfile
from app.services.prompt_renderer import PromptRenderer


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
            context = {
                "conversion_goal": experiment.conversion_goal,
                "target_audience": experiment.target_audience,
                "num_personas": current_batch_size,
                "existing_personas": existing_personas,
                "control_image_description": "Local uploaded control screenshot.",
                "challenger_image_description": "Local uploaded challenger screenshot.",
                "experiment_context": {
                    "experiment_id": experiment.id,
                    "experiment_name": experiment.name,
                },
            }
            profiles = await self._generate_batch(context, current_batch_size)

            for profile in profiles:
                persona = Persona(experiment_id=experiment.id, **profile.model_dump())
                session.add(persona)
                created.append(persona)
                existing_personas.append({"name": profile.name, "occupation": profile.occupation})

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
            prompt = self.prompt_renderer.render("persona_generation.md", retry_context)
            profiles.extend(await self.llm_client.generate_personas(prompt, remaining))

        if len(profiles) < target_count:
            raise ValueError(f"Expected {target_count} personas, got {len(profiles)} after retries")
        return profiles[:target_count]
