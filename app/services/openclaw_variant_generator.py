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

    agent_prompt_files = {
        "product_manager": Path("openclaw/agents/product_manager.md"),
        "ux_designer": Path("openclaw/agents/ux_designer.md"),
        "ux_researcher": Path("openclaw/agents/ux_researcher.md"),
        "critic": Path("openclaw/agents/critic.md"),
    }
    skill_prompt_files = {
        "hypothesis_scorer": Path("openclaw/skills/hypothesis_scorer/SKILL.md"),
        "mockup_generator": Path("openclaw/skills/mockup_generator/SKILL.md"),
    }

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
        headers = {}
        if settings.openclaw_gateway_token:
            headers["Authorization"] = f"Bearer {settings.openclaw_gateway_token}"

        logger.info(
            "Starting OpenClaw pipeline experiment_id=%s base_url=%s token_present=%s",
            payload.get("experiment_id"),
            settings.openclaw_base_url,
            bool(settings.openclaw_gateway_token),
        )
        async with httpx.AsyncClient(timeout=settings.openclaw_timeout_seconds) as client:
            pm_output = await self._call_pipeline_step(
                client=client,
                url=url,
                headers=headers,
                payload=payload,
                model="openclaw/product_manager",
                step="product_manager",
                instructions=self._read_prompt_file(self.agent_prompt_files["product_manager"]),
                context={},
                include_image=True,
            )
            ux_designer_output = await self._call_pipeline_step(
                client=client,
                url=url,
                headers=headers,
                payload=payload,
                model="openclaw/ux_designer",
                step="ux_designer",
                instructions=self._read_prompt_file(self.agent_prompt_files["ux_designer"]),
                context={},
                include_image=True,
            )
            ux_researcher_output = await self._call_pipeline_step(
                client=client,
                url=url,
                headers=headers,
                payload=payload,
                model="openclaw/ux_researcher",
                step="ux_researcher",
                instructions=self._read_prompt_file(self.agent_prompt_files["ux_researcher"]),
                context={},
                include_image=True,
            )
            scorer_output = await self._call_pipeline_step(
                client=client,
                url=url,
                headers=headers,
                payload=payload,
                model="openclaw/product_manager",
                step="hypothesis_scorer",
                instructions=self._read_prompt_file(self.skill_prompt_files["hypothesis_scorer"]),
                context={
                    "pm_output": pm_output,
                    "ux_designer_output": ux_designer_output,
                    "ux_researcher_output": ux_researcher_output,
                    "top_n": 3,
                },
                include_image=False,
            )
            selected_hypothesis = self._select_hypothesis(scorer_output)
            mockup_output = await self._call_pipeline_step(
                client=client,
                url=url,
                headers=headers,
                payload=payload,
                model="openclaw/ux_designer",
                step="mockup_generator",
                instructions=self._read_prompt_file(self.skill_prompt_files["mockup_generator"]),
                context={"selected_hypothesis": selected_hypothesis},
                include_image=True,
            )
            critic_output = await self._call_pipeline_step(
                client=client,
                url=url,
                headers=headers,
                payload=payload,
                model="openclaw/critic",
                step="critic",
                instructions=self._read_prompt_file(self.agent_prompt_files["critic"]),
                context={
                    "selected_hypothesis": selected_hypothesis,
                    "test_mockup": mockup_output,
                },
                include_image=True,
            )

        result = self._build_pipeline_response(
            pm_output=pm_output,
            ux_designer_output=ux_designer_output,
            ux_researcher_output=ux_researcher_output,
            scorer_output=scorer_output,
            selected_hypothesis=selected_hypothesis,
            mockup_output=mockup_output,
            critic_output=critic_output,
        )
        logger.info(
            "OpenClaw pipeline completed experiment_id=%s selected_title=%r final_decision=%r hypotheses=%s",
            payload.get("experiment_id"),
            selected_hypothesis.get("title"),
            critic_output.get("final_decision"),
            len(result.get("hypotheses") or []),
        )
        return result

    async def _call_pipeline_step(
        self,
        *,
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
        prompt = self._render_step_prompt(
            payload=payload,
            step=step,
            instructions=instructions,
            context=context,
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if include_image:
            content.append(self._image_content(payload))
        request_json = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.2,
        }
        logger.info(
            "Sending OpenClaw pipeline step experiment_id=%s step=%s model=%s prompt_chars=%s include_image=%s",
            payload.get("experiment_id"),
            step,
            model,
            len(prompt),
            include_image,
        )
        response = await client.post(url, json=request_json, headers=headers)
        logger.info(
            "OpenClaw pipeline step response experiment_id=%s step=%s status=%s bytes=%s",
            payload.get("experiment_id"),
            step,
            response.status_code,
            len(response.content or b""),
        )
        response.raise_for_status()
        result = self._parse_gateway_payload(response.json())
        logger.info(
            "OpenClaw pipeline step parsed experiment_id=%s step=%s keys=%s",
            payload.get("experiment_id"),
            step,
            sorted(result.keys()),
        )
        return result

    def _render_step_prompt(
        self,
        *,
        payload: dict[str, Any],
        step: str,
        instructions: str,
        context: dict[str, Any],
    ) -> str:
        base_context = {
            "goal": payload.get("conversion_goal") or "",
            "audience": payload.get("target_audience") or "",
            "control_mockup": payload["control_image"]["filename"],
            "product_context": payload.get("name") or "",
        }
        template_values = {**base_context, **context}
        rendered = instructions
        for key, value in template_values.items():
            rendered = rendered.replace("{{" + key + "}}", self._stringify_prompt_value(value))
        return (
            f"{rendered}\n\n"
            "## Runtime contract\n"
            f"- Pipeline step: {step}\n"
            "- Верни только валидный JSON без markdown-блоков и без пояснений вокруг JSON.\n"
            "- Если данных не хватает, используй пустые строки или осторожные предположения, но сохрани JSON-схему.\n"
        )

    @staticmethod
    def _stringify_prompt_value(value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value)

    @staticmethod
    def _image_content(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "image_url",
            "image_url": {
                "url": (
                    f"data:{payload['control_image']['mime_type']};base64,"
                    f"{payload['control_image']['data_base64']}"
                )
            },
        }

    @staticmethod
    def _read_prompt_file(path: Path) -> str:
        if not path.exists():
            raise FileNotFoundError(f"OpenClaw prompt file not found: {path}")
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _select_hypothesis(scorer_output: dict[str, Any]) -> dict[str, Any]:
        top_hypotheses = scorer_output.get("top_hypotheses")
        if isinstance(top_hypotheses, list) and top_hypotheses:
            first = top_hypotheses[0]
            if isinstance(first, dict):
                return first
        scored_hypotheses = scorer_output.get("scored_hypotheses")
        if isinstance(scored_hypotheses, list) and scored_hypotheses:
            first = scored_hypotheses[0]
            if isinstance(first, dict):
                return first
        raise ValueError("Hypothesis scorer returned no selectable hypothesis")

    @staticmethod
    def _build_pipeline_response(
        *,
        pm_output: dict[str, Any],
        ux_designer_output: dict[str, Any],
        ux_researcher_output: dict[str, Any],
        scorer_output: dict[str, Any],
        selected_hypothesis: dict[str, Any],
        mockup_output: dict[str, Any],
        critic_output: dict[str, Any],
    ) -> dict[str, Any]:
        top_hypotheses = scorer_output.get("top_hypotheses") or []
        hypotheses = []
        if isinstance(top_hypotheses, list):
            for item in top_hypotheses:
                if isinstance(item, dict):
                    hypotheses.append(
                        {
                            "title": item.get("title") or f"Hypothesis {item.get('id', '')}".strip(),
                            "rationale": item.get("why_selected") or item.get("hypothesis") or "",
                            "hypothesis": item.get("hypothesis") or "",
                            "proposed_change": item.get("proposed_change") or "",
                        }
                    )
        variant_direction = {
            "name": mockup_output.get("variant_name") or "Generated challenger",
            "summary": mockup_output.get("generation_instruction") or "",
            "key_changes": mockup_output.get("changes") or [],
        }
        return {
            "agent": "openclaw_pipeline",
            "status": "completed",
            "hypotheses": hypotheses,
            "variant_direction": variant_direction,
            "next_step": "user_selects_top_hypothesis",
            "selected_hypothesis": selected_hypothesis,
            "mockup_generator": mockup_output,
            "critic": critic_output,
            "pipeline": {
                "product_manager": pm_output,
                "ux_designer": ux_designer_output,
                "ux_researcher": ux_researcher_output,
                "hypothesis_scorer": scorer_output,
                "selected_hypothesis": selected_hypothesis,
                "mockup_generator": mockup_output,
                "critic": critic_output,
                "next_stage": "synthetic_ab",
            },
        }

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
