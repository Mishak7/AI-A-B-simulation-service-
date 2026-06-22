import base64
import json
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.llm.base import LLMClient
from app.llm.http_chat_client import HTTPChatClient
from app.schemas.persona import PersonaProfile
from app.schemas.simulation import SimulationVerdict, VisualAssessment

logger = logging.getLogger(__name__)


class RealLLMClient(LLMClient):
    """Direct HTTP client for the configured Qwen text/vision endpoint.

    Example config:
    SAB_QWEN_BASE_URL=https://45.9.24.84/v1
    SAB_QWEN_MODEL=Qwen3.5-397B-A17B-FP8
    """

    def __init__(self) -> None:
        settings = get_settings()
        api_key = settings.qwen_api_key
        model = settings.qwen_model

        if not api_key:
            raise ValueError("SAB_QWEN_API_KEY is required when SAB_LLM_PROVIDER=real")

        self.client = HTTPChatClient(
            api_key=api_key,
            base_url=settings.qwen_base_url,
            model=model,
            timeout_seconds=settings.real_timeout_seconds,
            max_retries=settings.qwen_max_retries,
            initial_concurrency=settings.qwen_initial_concurrency,
            max_concurrency=settings.qwen_max_concurrency,
            increase_after_successes=settings.qwen_increase_after_successes,
            min_interval_seconds=settings.qwen_min_interval_seconds,
            max_interval_seconds=settings.qwen_max_interval_seconds,
            max_retry_delay_seconds=settings.qwen_max_retry_delay_seconds,
        )
        self.model = model
        self.base_url = settings.qwen_base_url
        self.timeout_seconds = settings.real_timeout_seconds
        self.max_retries = settings.qwen_max_retries
        logger.info(
            "Initialized RealLLMClient base_url=%s model=%s timeout_seconds=%s max_retries=%s",
            self.base_url,
            self.model,
            self.timeout_seconds,
            self.max_retries,
        )

    async def generate_personas(self, prompt: str, num_personas: int) -> list[PersonaProfile]:
        logger.info("Calling real LLM for persona generation num_personas=%s", num_personas)
        response_text = await self._chat_text(prompt)
        payload = self._extract_json(response_text)
        personas_payload = payload.get("personas", payload) if isinstance(payload, dict) else payload
        if not isinstance(personas_payload, list):
            raise ValueError("Persona generation response must be a JSON array or an object with personas[]")

        personas = [PersonaProfile.model_validate(item) for item in personas_payload[:num_personas]]
        if len(personas) != num_personas:
            logger.info(
                "Real LLM returned %s/%s personas; PersonaGenerator will request the missing profiles",
                len(personas),
                num_personas,
            )
        return personas

    async def simulate_choice(
        self,
        prompt: str,
        control_image_path: str,
        challenger_image_path: str,
        context: dict[str, Any],
    ) -> SimulationVerdict:
        logger.info(
            "Calling real VLM for neutralized pairwise simulation image_1_source=%s image_2_source=%s",
            context.get("image_1_source"),
            context.get("image_2_source"),
        )
        content = [
            {"type": "text", "text": prompt},
            {"type": "text", "text": "Image 1:"},
            self._image_content_part(
                control_image_path
                if context.get("image_1_source") == "Control"
                else challenger_image_path
            ),
            {"type": "text", "text": "Image 2:"},
            self._image_content_part(
                challenger_image_path
                if context.get("image_2_source") == "Challenger"
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
        logger.debug(
            "Sending direct HTTP chat request model=%s base_url=%s",
            self.model,
            self.base_url,
        )
        return await self.client.complete(
            content,
            temperature=0.2,
            max_tokens=get_settings().qwen_max_tokens,
        )

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
