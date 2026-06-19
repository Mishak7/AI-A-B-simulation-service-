import base64
import json
import logging
import mimetypes
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.models import Experiment
from app.services.image_edit_client import ImageEditClient

logger = logging.getLogger(__name__)


class OpenClawVariantGenerator:
    """Discuss hypotheses in OpenClaw, then generate one image variant directly."""

    agent_prompt_files = {
        "product_manager": Path("openclaw/agents/product_manager.md"),
        "ux_designer": Path("openclaw/agents/ux_designer.md"),
        "ux_researcher": Path("openclaw/agents/ux_researcher.md"),
    }
    skill_prompt_files = {
        "hypothesis_scorer": Path("openclaw/skills/hypothesis_scorer/SKILL.md"),
    }

    async def start(self, experiment: Experiment, batch_size: int) -> dict[str, Any]:
        payload = self._build_payload(experiment, batch_size, mode="variant_generation")
        settings = get_settings()
        experiment_dir = settings.storage_dir / str(experiment.id)
        experiment_dir.mkdir(parents=True, exist_ok=True)
        request_path = experiment_dir / "openclaw_request.json"
        response_path = experiment_dir / "openclaw_response.json"
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
        agent_response = await self._generate_hypotheses(payload)
        response_path.write_text(
            json.dumps(agent_response, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {
            "experiment_id": experiment.id,
            "status": "hypotheses_ready",
            "message": "Агенты обсудили контрольный макет и сформулировали top-гипотезы.",
            "request_path": str(request_path),
            "response_path": str(response_path),
            "runtime": "openclaw_gateway",
            "agent_response": agent_response,
        }

    async def generate_variant_image(
        self,
        experiment: Experiment,
        selected_hypothesis: dict[str, Any],
        generation_prompt: str | None = None,
    ) -> dict[str, Any]:
        payload = self._build_payload(experiment, batch_size=1, mode="image_generation")
        settings = get_settings()
        prompt = self._build_image_prompt(
            selected_hypothesis=selected_hypothesis,
            generation_prompt=generation_prompt,
        )
        experiment_dir = settings.storage_dir / str(experiment.id)
        experiment_dir.mkdir(parents=True, exist_ok=True)
        control_path = Path(experiment.control_image_path or "")
        logger.info(
            "Calling image edit model experiment_id=%s endpoint=%s%s model=%s "
            "quality=%s input_fidelity=%s prompt=%r",
            experiment.id,
            settings.image_base_url.rstrip("/"),
            settings.image_edit_endpoint_path,
            settings.image_model,
            settings.image_quality,
            settings.image_input_fidelity,
            prompt,
        )
        generated = await ImageEditClient(settings).edit(
            control_image_path=control_path,
            prompt=prompt,
            output_dir=experiment_dir,
        )

        response_path = experiment_dir / "image_generation_response.json"
        response_record = {
            "selected_hypothesis_title": str(selected_hypothesis.get("title") or ""),
            "generation_prompt": prompt,
            "generation": {
                "model": settings.image_model,
                "size": generated.size,
                "quality": settings.image_quality,
                "input_fidelity_used": generated.input_fidelity_used,
                "mode": "images_edit",
                "response_shape": generated.response_shape,
            },
            "control_image": {
                "filename": payload["control_image"]["filename"],
                "mime_type": payload["control_image"]["mime_type"],
                "width": generated.source_width,
                "height": generated.source_height,
            },
            "challenger_image_path": str(generated.output_path),
            "challenger_image_url": f"/experiments/{experiment.id}/generated-variant",
            "provider_metadata": generated.provider_metadata,
            "generated_at": datetime.now(UTC).isoformat(),
        }
        response_path.write_text(
            json.dumps(response_record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(
            "Image edit model completed experiment_id=%s model=%s response_shape=%s "
            "size=%s output=%s",
            experiment.id,
            settings.image_model,
            generated.response_shape,
            generated.size,
            generated.output_path,
        )
        return {
            "experiment_id": experiment.id,
            "status": "variant_ready",
            "message": "Тестовый вариант создан через Images API.",
            "response_path": str(response_path),
            "challenger_image_path": str(generated.output_path),
            "challenger_image_url": response_record["challenger_image_url"],
            "runtime": "images_edit",
            "agent_response": response_record,
        }

    async def _generate_hypotheses(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        if not settings.openclaw_base_url:
            raise ValueError("SAB_OPENCLAW_BASE_URL is required for agent discussion")
        try:
            import httpx
        except ImportError as exc:
            raise ImportError("Install httpx to call the OpenClaw container") from exc

        url = settings.openclaw_base_url.rstrip("/") + "/v1/chat/completions"
        headers = {}
        if settings.openclaw_gateway_token:
            headers["Authorization"] = f"Bearer {settings.openclaw_gateway_token}"

        async with httpx.AsyncClient(timeout=settings.openclaw_timeout_seconds) as client:
            pm_output = await self._call_pipeline_step(
                client, url, headers, payload, "openclaw/product_manager", "product_manager",
                self._read_prompt_file(self.agent_prompt_files["product_manager"]), {}, True,
            )
            ux_designer_output = await self._call_pipeline_step(
                client, url, headers, payload, "openclaw/ux_designer", "ux_designer",
                self._read_prompt_file(self.agent_prompt_files["ux_designer"]), {}, True,
            )
            ux_researcher_output = await self._call_pipeline_step(
                client, url, headers, payload, "openclaw/ux_researcher", "ux_researcher",
                self._read_prompt_file(self.agent_prompt_files["ux_researcher"]), {}, True,
            )
            scorer_output = await self._call_pipeline_step(
                client, url, headers, payload, "openclaw/product_manager", "hypothesis_scorer",
                self._read_prompt_file(self.skill_prompt_files["hypothesis_scorer"]),
                {
                    "pm_output": pm_output,
                    "ux_designer_output": ux_designer_output,
                    "ux_researcher_output": ux_researcher_output,
                    "top_n": 3,
                },
                False,
            )
        return self._build_pipeline_response(
            pm_output=pm_output,
            ux_designer_output=ux_designer_output,
            ux_researcher_output=ux_researcher_output,
            scorer_output=scorer_output,
        )

    async def _call_pipeline_step(
        self,
        client: Any,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        model: str,
        step: str,
        instructions: str,
        context: dict[str, Any],
        include_image: bool,
    ) -> dict[str, Any]:
        prompt = self._render_step_prompt(payload, step, instructions, context)
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if include_image:
            content.append(self._image_content(payload))
        response = await client.post(
            url,
            headers=headers,
            json={
                "model": model,
                "messages": [{"role": "user", "content": content}],
                "temperature": 0.2,
                "tools": [],
                "tool_choice": "none",
            },
        )
        response.raise_for_status()
        expected_keys = (
            {"top_hypotheses", "scored_hypotheses"}
            if step == "hypothesis_scorer"
            else None
        )
        return self._parse_gateway_payload(
            response.json(), expected_keys=expected_keys
        )

    def _render_step_prompt(
        self,
        payload: dict[str, Any],
        step: str,
        instructions: str,
        context: dict[str, Any],
    ) -> str:
        values = {
            "goal": payload.get("conversion_goal") or "",
            "audience": payload.get("target_audience") or "",
            "control_mockup": "Контрольный макет приложен к сообщению как image_url.",
            "product_context": payload.get("name") or "",
            **context,
        }
        rendered = instructions
        for key, value in values.items():
            rendered = rendered.replace("{{" + key + "}}", self._stringify(value))
        return (
            f"{rendered}\n\nPipeline step: {step}. "
            "Верни только валидный JSON без markdown и пояснений вокруг JSON."
        )

    @staticmethod
    def _build_image_prompt(
        *,
        selected_hypothesis: dict[str, Any],
        generation_prompt: str | None,
    ) -> str:
        requested_change = str(
            generation_prompt
            or selected_hypothesis.get("generation_prompt")
            or selected_hypothesis.get("proposed_change")
            or selected_hypothesis.get("hypothesis")
            or "Apply the selected A/B hypothesis"
        ).strip()
        if not requested_change:
            requested_change = "Apply the selected A/B hypothesis"
        return (
            "Edit the attached UI screenshot. "
            f"Make exactly this change: {requested_change}. "
            "Keep everything else unchanged: layout, text, numbers, colors, images, and resolution. "
            "Do not add any other elements, captions, explanations, or watermarks."
        )

    @staticmethod
    def _build_payload(experiment: Experiment, batch_size: int, mode: str) -> dict[str, Any]:
        if not experiment.control_image_path:
            raise ValueError("Control image is required for variant generation")
        image_path = Path(experiment.control_image_path)
        image_bytes = image_path.read_bytes()
        return {
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
            "metadata": {"mode": mode, "created_at": datetime.now(UTC).isoformat()},
        }

    @classmethod
    def _build_pipeline_response(
        cls,
        *,
        pm_output: dict[str, Any],
        ux_designer_output: dict[str, Any],
        ux_researcher_output: dict[str, Any],
        scorer_output: dict[str, Any],
    ) -> dict[str, Any]:
        selected_items = scorer_output.get("top_hypotheses") or []
        if not selected_items:
            scored_items = scorer_output.get("scored_hypotheses") or []
            if isinstance(scored_items, list):
                selected_items = sorted(
                    (item for item in scored_items if isinstance(item, dict)),
                    key=lambda item: float(item.get("score") or 0),
                    reverse=True,
                )[:3]
        hypotheses = []
        for item in selected_items:
            if not isinstance(item, dict):
                continue
            hypothesis = {
                "title": item.get("title") or f"Hypothesis {item.get('id', '')}".strip(),
                "rationale": item.get("why_selected") or item.get("hypothesis") or "",
                "hypothesis": item.get("hypothesis") or "",
                "proposed_change": item.get("proposed_change") or "",
            }
            hypothesis["generation_prompt"] = str(
                hypothesis["proposed_change"] or hypothesis["hypothesis"]
            ).strip()
            hypotheses.append(hypothesis)
        if not hypotheses:
            raise ValueError(
                "Hypothesis scorer returned no usable top_hypotheses or scored_hypotheses"
            )
        return {
            "agent": "openclaw_pipeline",
            "status": "hypotheses_ready",
            "hypotheses": hypotheses[:3],
            "next_step": "user_selects_hypothesis_for_image_generation",
            "pipeline": {
                "product_manager": pm_output,
                "ux_designer": ux_designer_output,
                "ux_researcher": ux_researcher_output,
                "hypothesis_scorer": scorer_output,
                "next_stage": "direct_image_generation",
            },
        }

    @staticmethod
    def _image_content(payload: dict[str, Any]) -> dict[str, Any]:
        image = payload["control_image"]
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{image['mime_type']};base64,{image['data_base64']}"},
        }

    @staticmethod
    def _read_prompt_file(path: Path) -> str:
        if not path.exists():
            raise FileNotFoundError(f"OpenClaw prompt file not found: {path}")
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _stringify(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (dict, list)) else str(value)

    @staticmethod
    def _parse_gateway_payload(
        payload: dict[str, Any],
        expected_keys: set[str] | None = None,
    ) -> dict[str, Any]:
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("OpenClaw response is not chat.completions-compatible") from exc
        if isinstance(content, list):
            content = "\n".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        stripped = str(content or "").strip()
        objects = OpenClawVariantGenerator._decode_json_objects(stripped)
        if not objects:
            raise ValueError("OpenClaw content does not contain a valid JSON object")
        if expected_keys:
            matching = [
                item for item in objects if expected_keys.intersection(item.keys())
            ]
            if not matching:
                keys = ", ".join(sorted(expected_keys))
                raise ValueError(
                    f"OpenClaw response does not contain expected JSON keys: {keys}"
                )
            result = matching[0]
        else:
            result = objects[0]
        if len(objects) > 1:
            logger.warning(
                "OpenClaw response contained multiple JSON objects; selected_keys=%s objects=%s",
                sorted(result.keys()),
                len(objects),
            )
        return result

    @staticmethod
    def _decode_json_objects(text: str) -> list[dict[str, Any]]:
        decoder = json.JSONDecoder()
        objects: list[dict[str, Any]] = []
        consumed_ranges: list[tuple[int, int]] = []
        for match in re.finditer(r"\{", text):
            start = match.start()
            if any(range_start < start < range_end for range_start, range_end in consumed_ranges):
                continue
            try:
                result, end = decoder.raw_decode(text, start)
            except json.JSONDecodeError:
                continue
            if isinstance(result, dict):
                objects.append(result)
                consumed_ranges.append((start, end))
        return objects
