from abc import ABC, abstractmethod
from typing import Any

from app.schemas.persona import PersonaProfile
from app.schemas.simulation import SimulationVerdict, VisualAssessment


class LLMClient(ABC):
    @abstractmethod
    async def generate_personas(self, prompt: str, num_personas: int) -> list[PersonaProfile]:
        raise NotImplementedError

    @abstractmethod
    async def simulate_choice(
        self,
        prompt: str,
        control_image_path: str,
        challenger_image_path: str,
        context: dict[str, Any],
    ) -> SimulationVerdict:
        raise NotImplementedError

    @abstractmethod
    async def assess_visual_quality(self, prompt: str, image_path: str, image_label: str) -> VisualAssessment:
        raise NotImplementedError

    @abstractmethod
    async def summarize_report(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
