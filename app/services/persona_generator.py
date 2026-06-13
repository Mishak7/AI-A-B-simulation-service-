from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMClient
from app.models import Experiment, Persona
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
            prompt = self.prompt_renderer.render("persona_generation.md", context)
            profiles = await self.llm_client.generate_personas(prompt, current_batch_size)

            for profile in profiles:
                persona = Persona(experiment_id=experiment.id, **profile.model_dump())
                session.add(persona)
                created.append(persona)
                existing_personas.append({"name": profile.name, "occupation": profile.occupation})

            await session.flush()

        return created
