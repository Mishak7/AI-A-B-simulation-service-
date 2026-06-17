import json
import logging
import mimetypes
import base64
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.models import Experiment

logger = logging.getLogger(__name__)


class OpenClawVariantGenerator:
    """Boundary for the OpenClaw agent workflow."""

    async def start(self, experiment: Experiment, batch_size: int) -> dict[str, Any]:
        if not experiment.control_image_path:
            raise ValueError("Control image is required for variant generation")

        settings = get_settings()
        experiment_dir = settings.storage_dir / str(experiment.id)
        experiment_dir.mkdir(parents=True, exist_ok=True)
        request_path = experiment_dir / "openclaw_request.json"
        response_path = experiment_dir / "openclaw_response.json"
        image_path = Path(experiment.control_image_path)
        image_bytes = image_path.read_bytes()
        payload = {
            "experiment_id": experiment.id,
            "name": experiment.name,
            "conversion_goal": experiment.conversion_goal,
            "target_audience": experiment.target_audience,
            "batch_size": batch_size,
            "control_image": {
                "filename": image_path.name,
                "mime_type": mimetypes.guess_type(image_path.name)[0] or "image/png",
                "source_path": experiment.control_image_path,
                "data_base64": base64.b64encode(image_bytes).decode("ascii"),
            },
            "metadata": {
                "mode": "variant_generation",
                "created_at": datetime.now(UTC).isoformat(),
            },
        }
        request_record = {
            **payload,
            "created_at": datetime.now(UTC).isoformat(),
            "integration": {
                "runtime": "openclaw_gateway",
                "transport": "openai_compatible_chat_completions",
                "base_url": settings.openclaw_base_url,
                "model": settings.openclaw_model,
            },
        }
        request_path.write_text(
            json.dumps(request_record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(
            "OpenClaw request prepared experiment_id=%s runtime=%s image_filename=%s image_bytes=%s image_b64_chars=%s goal_chars=%s audience_chars=%s",
            experiment.id,
            request_record["integration"]["runtime"],
            image_path.name,
            len(image_bytes),
            len(payload["control_image"]["data_base64"]),
            len(experiment.conversion_goal or ""),
            len(experiment.target_audience or ""),
        )
        agent_response = await self._call_openclaw(payload)
        response_path.write_text(
            json.dumps(agent_response, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(
            "OpenClaw variant generation completed experiment_id=%s request_path=%s response_path=%s runtime=%s",
            experiment.id,
            request_path,
            response_path,
            request_record["integration"]["runtime"],
        )
        return {
            "experiment_id": experiment.id,
            "status": "completed_openclaw",
            "message": (
                "OpenClaw получил поля и контрольный макет, вернул первые гипотезы "
                "и направление тестового варианта."
            ),
            "request_path": str(Path(request_path)),
            "response_path": str(Path(response_path)),
            "runtime": request_record["integration"]["runtime"],
            "agent_response": agent_response,
        }

    async def _call_openclaw(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        if not settings.openclaw_base_url:
            raise ValueError("SAB_OPENCLAW_BASE_URL is required for OpenClaw generation")

        try:
            import httpx
        except ImportError as exc:
            raise ImportError("Install httpx to call the OpenClaw container") from exc

        url = settings.openclaw_base_url.rstrip("/") + "/v1/chat/completions"
        prompt = self._render_prompt(payload)
        request_json = {
            "model": settings.openclaw_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": (
                                    f"data:{payload['control_image']['mime_type']};base64,"
                                    f"{payload['control_image']['data_base64']}"
                                )
                            },
                        },
                    ],
                }
            ],
            "temperature": 0.2,
        }
        headers = {}
        if settings.openclaw_gateway_token:
            headers["Authorization"] = f"Bearer {settings.openclaw_gateway_token}"
        logger.info(
            "Sending OpenClaw Gateway request url=%s experiment_id=%s model=%s token_present=%s prompt_chars=%s image_b64_chars=%s",
            url,
            payload.get("experiment_id"),
            settings.openclaw_model,
            bool(settings.openclaw_gateway_token),
            len(prompt),
            len(payload["control_image"]["data_base64"]),
        )
        async with httpx.AsyncClient(timeout=settings.openclaw_timeout_seconds) as client:
            response = await client.post(url, json=request_json, headers=headers)
            logger.info(
                "OpenClaw Gateway response status=%s bytes=%s experiment_id=%s",
                response.status_code,
                len(response.content or b""),
                payload.get("experiment_id"),
            )
            response.raise_for_status()
            gateway_payload = response.json()
        result = self._parse_gateway_payload(gateway_payload)
        logger.info(
            "OpenClaw Gateway response parsed experiment_id=%s agent=%s hypotheses=%s",
            payload.get("experiment_id"),
            result.get("agent"),
            len(result.get("hypotheses") or []),
        )
        return result

    @staticmethod
    def _render_prompt(payload: dict[str, Any]) -> str:
        return (
            "Ты OpenClaw-агент для генерации продуктовых A/B гипотез по контрольному макету. "
            "Проанализируй поля эксперимента и изображение. Верни только JSON без markdown. "
            "Схема JSON: {"
            "\"agent\":\"openclaw_gateway\","
            "\"status\":\"completed\","
            "\"hypotheses\":[{\"title\":\"...\",\"rationale\":\"...\"}],"
            "\"variant_direction\":{\"name\":\"...\",\"summary\":\"...\"},"
            "\"next_step\":\"...\""
            "}. "
            f"Название: {payload.get('name') or 'не указано'}. "
            f"Цель: {payload.get('conversion_goal') or 'не указана'}. "
            f"Аудитория: {payload.get('target_audience') or 'не указана'}."
        )

    @staticmethod
    def _parse_gateway_payload(gateway_payload: dict[str, Any]) -> dict[str, Any]:
        try:
            content = gateway_payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("OpenClaw Gateway response is not chat.completions-compatible") from exc
        if not content:
            raise ValueError("OpenClaw Gateway returned empty content")

        stripped = str(content).strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            stripped = fenced.group(1).strip()
        try:
            result = json.loads(stripped)
        except json.JSONDecodeError:
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start == -1 or end <= start:
                raise
            result = json.loads(stripped[start : end + 1])
        if not isinstance(result, dict):
            raise ValueError("OpenClaw Gateway content must be a JSON object")
        result.setdefault("agent", "openclaw_gateway")
        result.setdefault("status", "completed")
        return result
