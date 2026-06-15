import base64
import json
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.llm.base import LLMClient
from app.schemas.persona import PersonaProfile
from app.schemas.simulation import SimulationVerdict, VisualAssessment

logger = logging.getLogger(__name__)


class RealLLMClient(LLMClient):
    """OpenAI-compatible client for third-party LLM gateways.

    Example gateway config:
    SAB_REAL_BASE_URL=https://api.vsellm.ru/v1
    SAB_REAL_MODEL=google/gemini-2.5-flash
    """

    def __init__(self) -> None:
        settings = get_settings()
        api_key = settings.real_api_key or settings.gemini_api_key
        model = settings.real_model or settings.gemini_model or "google/gemini-2.5-flash"

        if not api_key:
            raise ValueError("SAB_REAL_API_KEY is required when SAB_LLM_PROVIDER=real")

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("Install openai to use RealLLMClient: pip install openai") from exc

        self.client = AsyncOpenAI(api_key=api_key, base_url=settings.real_base_url)
        self.model = model
        self.base_url = settings.real_base_url
        logger.info("Initialized RealLLMClient base_url=%s model=%s", self.base_url, self.model)

    async def generate_personas(self, prompt: str, num_personas: int) -> list[PersonaProfile]:
        logger.info("Calling real LLM for persona generation num_personas=%s", num_personas)
        response_text = await self._chat_text(prompt)
        payload = self._extract_json(response_text)
        personas_payload = payload.get("personas", payload) if isinstance(payload, dict) else payload
        if not isinstance(personas_payload, list):
            raise ValueError("Persona generation response must be a JSON array or an object with personas[]")

        personas = [PersonaProfile.model_validate(item) for item in personas_payload[:num_personas]]
        if len(personas) != num_personas:
            raise ValueError(f"Expected {num_personas} personas, got {len(personas)}")
        return personas

    async def simulate_choice(
        self,
        prompt: str,
        control_image_path: str,
        challenger_image_path: str,
        context: dict[str, Any],
    ) -> SimulationVerdict:
        logger.info(
            "Calling real VLM for simulation presented_order=%s image_1=%s image_2=%s",
            context.get("presented_order"),
            context.get("image_1_label"),
            context.get("image_2_label"),
        )
        content = [
            {"type": "text", "text": prompt},
            {"type": "text", "text": "Image 1:"},
            self._image_content_part(
                control_image_path
                if context.get("image_1_label") == "Control"
                else challenger_image_path
            ),
            {"type": "text", "text": "Image 2:"},
            self._image_content_part(
                challenger_image_path
                if context.get("image_2_label") == "Challenger"
                else control_image_path
            ),
        ]
        response_text = await self._chat_content(content)
        payload = self._extract_json(response_text)
        return SimulationVerdict.model_validate(payload)

    async def assess_visual_quality(self, prompt: str, image_path: str, image_label: str) -> VisualAssessment:
        logger.info("Calling real VLM for single-image visual QA image_label=%s", image_label)
        content = [
            {"type": "text", "text": prompt},
            {"type": "text", "text": f"{image_label} screenshot:"},
            self._image_content_part(image_path),
        ]
        response_text = await self._chat_content(content)
        payload = self._extract_json(response_text)
        return VisualAssessment.model_validate(payload)

    async def summarize_report(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        logger.info("Calling real LLM for report summary winner=%s", context.get("winner"))
        response_text = await self._chat_text(prompt)
        payload = self._extract_json(response_text)
        if not isinstance(payload, dict):
            raise ValueError("Report summary response must be a JSON object")
        payload.setdefault("limitations", "Синтетическая оценка не заменяет реальный A/B-тест.")
        payload.setdefault("recommendations", [])
        return payload

    async def _chat_text(self, prompt: str) -> str:
        return await self._chat_content(prompt)

    async def _chat_content(self, content: str | list[dict[str, Any]]) -> str:
        logger.debug("Sending chat.completions request model=%s base_url=%s", self.model, self.base_url)
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": content,
                }
            ],
            temperature=0.2,
        )
        message = response.choices[0].message.content
        if not message:
            raise ValueError("LLM returned an empty response")
        return message

    @staticmethod
    def _image_content_part(image_path: str) -> dict[str, Any]:
        path = Path(image_path)
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{encoded}",
            },
        }

    @staticmethod
    def _extract_json(text: str) -> Any:
        stripped = text.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            stripped = fenced.group(1).strip()

        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            start_candidates = [idx for idx in (stripped.find("{"), stripped.find("[")) if idx != -1]
            if not start_candidates:
                raise
            start = min(start_candidates)
            end = max(stripped.rfind("}"), stripped.rfind("]"))
            if end <= start:
                raise
            return json.loads(stripped[start : end + 1])
