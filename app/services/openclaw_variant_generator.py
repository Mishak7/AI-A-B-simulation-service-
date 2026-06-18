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
        agent_response = await self._generate_hypotheses(payload)
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
            "status": "hypotheses_ready",
            "message": (
                "OpenClaw проанализировал контрольный макет и вернул top-гипотезы "
                "для выбора."
            ),
            "request_path": str(Path(request_path)),
            "response_path": str(Path(response_path)),
            "runtime": request_record["integration"]["runtime"],
            "agent_response": agent_response,
        }

    async def generate_mockup(
        self,
        experiment: Experiment,
        selected_hypothesis: dict[str, Any],
        batch_size: int,
    ) -> dict[str, Any]:
        if not experiment.control_image_path:
            raise ValueError("Control image is required for variant generation")

        settings = get_settings()
        experiment_dir = settings.storage_dir / str(experiment.id)
        experiment_dir.mkdir(parents=True, exist_ok=True)
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
                "mode": "variant_mockup_generation",
                "created_at": datetime.now(UTC).isoformat(),
            },
        }
        result = await self._generate_mockup_with_critic(payload, selected_hypothesis)
        challenger_mime = result["generated_image"]["mime_type"]
        challenger_path = experiment_dir / f"challenger{self._image_suffix(challenger_mime)}"
        challenger_path.write_bytes(base64.b64decode(result["generated_image"]["data_base64"]))
        response_path = experiment_dir / "openclaw_mockup_response.json"
        response_record = {
            **result,
            "selected_hypothesis": selected_hypothesis,
            "challenger_image_path": str(challenger_path),
            "challenger_image_data_url": self._image_data_url(
                mime_type=challenger_mime,
                data_base64=result["generated_image"]["data_base64"],
            ),
        }
        response_record["generated_image"] = {
            "mime_type": challenger_mime,
            "bytes": len(challenger_path.read_bytes()),
        }
        response_path.write_text(
            json.dumps(response_record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "OpenClaw image mockup generation completed experiment_id=%s challenger=%s mime=%s attempts=%s decision=%s",
            experiment.id,
            challenger_path,
            challenger_mime,
            len(result["critic_attempts"]),
            result["critic"].get("final_decision"),
        )
        return {
            "experiment_id": experiment.id,
            "status": "mockup_ready",
            "message": "Тестовый макет подготовлен и проверен critic-агентом.",
            "response_path": str(response_path),
            "challenger_image_path": str(challenger_path),
            "challenger_image_data_url": response_record["challenger_image_data_url"],
            "runtime": "openclaw_gateway",
            "agent_response": response_record,
        }

    async def _generate_hypotheses(self, payload: dict[str, Any]) -> dict[str, Any]:
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

        result = self._build_pipeline_response(
            pm_output=pm_output,
            ux_designer_output=ux_designer_output,
            ux_researcher_output=ux_researcher_output,
            scorer_output=scorer_output,
        )
        logger.info(
            "OpenClaw hypothesis pipeline completed experiment_id=%s hypotheses=%s",
            payload.get("experiment_id"),
            len(result.get("hypotheses") or []),
        )
        return result

    async def _generate_mockup_with_critic(
        self,
        payload: dict[str, Any],
        selected_hypothesis: dict[str, Any],
    ) -> dict[str, Any]:
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

        critic_attempts = []
        revision_notes: list[str] = []
        generated_image: dict[str, str] | None = None
        async with httpx.AsyncClient(timeout=settings.openclaw_timeout_seconds) as client:
            for attempt in range(1, 4):
                mockup_output = await self._call_html_mockup_step(
                    client=client,
                    url=url,
                    headers=headers,
                    payload=payload,
                    step=f"html_mockup_generator_attempt_{attempt}",
                    instructions=self._read_prompt_file(self.skill_prompt_files["mockup_generator"]),
                    context={
                        "selected_hypothesis": selected_hypothesis,
                        "revision_notes": revision_notes,
                    },
                )
                rendered = await self._render_html_to_png(
                    html=mockup_output["variant_html"],
                    payload=payload,
                    step=f"html_mockup_render_attempt_{attempt}",
                )
                generated_image = {
                    "mime_type": "image/png",
                    "data_base64": rendered["data_base64"],
                }
                mockup_output["rendered_mockup_path"] = rendered["path"]
                generated_image_content = {
                    "type": "image_url",
                    "image_url": {
                        "url": self._image_data_url(
                            mime_type=generated_image["mime_type"],
                            data_base64=generated_image["data_base64"],
                        )
                    },
                }
                critic_output = await self._call_pipeline_step(
                    client=client,
                    url=url,
                    headers=headers,
                    payload=payload,
                    model="openclaw/critic",
                    step=f"critic_attempt_{attempt}",
                    instructions=self._read_prompt_file(self.agent_prompt_files["critic"]),
                    context={
                        "selected_hypothesis": selected_hypothesis,
                        "test_mockup": mockup_output,
                    },
                    include_image=True,
                    extra_content=[
                        {"type": "text", "text": "Generated test mockup:"},
                        generated_image_content,
                    ],
                )
                critic_attempts.append(
                    {
                        "attempt": attempt,
                        "mockup_generator": self._strip_render_payload(mockup_output),
                        "critic": critic_output,
                    }
                )
                decision = str(critic_output.get("final_decision") or "").lower()
                is_valid = bool(critic_output.get("is_valid"))
                if is_valid or decision == "accept":
                    break
                revision_notes = critic_output.get("recommendations") or critic_output.get("problems") or []
                if not isinstance(revision_notes, list):
                    revision_notes = [str(revision_notes)]
        return {
            "mockup_generator": critic_attempts[-1]["mockup_generator"],
            "critic": critic_attempts[-1]["critic"],
            "critic_attempts": critic_attempts,
            "generated_image": generated_image,
        }

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
        extra_content: list[dict[str, Any]] | None = None,
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
        if extra_content:
            content.extend(extra_content)
        request_json = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.2,
            "tools": [],
            "tool_choice": "none",
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

    async def _call_html_mockup_step(
        self,
        *,
        client: Any,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        step: str,
        instructions: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = self._render_step_prompt(
            payload=payload,
            step=step,
            instructions=instructions,
            context=context,
        )
        prompt += (""
        )
        request_json = {
            "model": "openclaw/html_mockup_builder",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "text", "text": "Control mockup to edit:"},
                        self._image_content(payload),
                    ],
                }
            ],
            "temperature": 0.2,
            "tools": [],
            "tool_choice": "none",
        }
        logger.info(
            "Sending HTML mockup generation request experiment_id=%s step=%s model=%s prompt_chars=%s image_b64_chars=%s",
            payload.get("experiment_id"),
            step,
            request_json["model"],
            len(prompt),
            len(payload["control_image"]["data_base64"]),
        )
        response = await client.post(url, json=request_json, headers=headers)
        logger.info(
            "HTML mockup generation response experiment_id=%s step=%s status=%s bytes=%s",
            payload.get("experiment_id"),
            step,
            response.status_code,
            len(response.content or b""),
        )
        response.raise_for_status()
        response_payload = response.json()
        debug_path = (
                get_settings().storage_dir
                / str(payload.get("experiment_id"))
                / f"{step}_raw_html_response.json"
        )
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(
            json.dumps(response_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info(
            "HTML mockup raw response saved experiment_id=%s step=%s path=%s top_keys=%s",
            payload.get("experiment_id"),
            step,
            debug_path,
            sorted(response_payload.keys()) if isinstance(response_payload, dict) else type(response_payload).__name__,
        )
        mockup_output = self._extract_image_step_json(response_payload)
        mockup_output.setdefault("variant_name", "Generated image variant")
        mockup_output.setdefault("ready_for_generation", True)
        mockup_output["generation_mode"] = "html_css_playwright"
        try:
            mockup_output["variant_html"] = self._extract_variant_html(mockup_output)
        except ValueError:
            logger.warning(
                "HTML mockup response has no variant_html; requesting repair experiment_id=%s step=%s keys=%s",
                payload.get("experiment_id"),
                step,
                sorted(mockup_output.keys()),
            )
            repaired = await self._repair_html_mockup_step(
                client=client,
                url=url,
                headers=headers,
                payload=payload,
                step=f"{step}_repair",
                previous_output=mockup_output,
            )
            mockup_output = {**mockup_output, **repaired}
            mockup_output["generation_mode"] = "html_css_playwright_repair"
            mockup_output["variant_html"] = self._extract_variant_html(mockup_output)
        html_path = get_settings().storage_dir / str(payload.get("experiment_id")) / f"{step}.html"
        html_path.write_text(mockup_output["variant_html"], encoding="utf-8")
        mockup_output["variant_html_path"] = str(html_path)
        logger.info(
            "HTML mockup generation parsed experiment_id=%s step=%s html_chars=%s keys=%s",
            payload.get("experiment_id"),
            step,
            len(mockup_output["variant_html"]),
            sorted(mockup_output.keys()),
        )
        return mockup_output

    async def _repair_html_mockup_step(
        self,
        *,
        client: Any,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        step: str,
        previous_output: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = (
            "Предыдущий ответ не содержит обязательное поле variant_html.\n"
            "Сейчас нужно вернуть ТОЛЬКО валидный JSON без markdown.\n"
            "На основе приложенного контрольного изображения и previous_output сверстай полноценный HTML/CSS-макет с нуля.\n"
            "variant_html обязателен и должен быть полным HTML-документом с inline CSS: <!doctype html><html><head><style>...</style></head><body>...</body></html>.\n"
            "Контрольный скриншот — только визуальный референс, не используй его как img, background-image, canvas или overlay-подложку.\n"
            "Макет должен максимально повторять контрольный экран и содержать только изменение из previous_output.changes.\n"
            "Не добавляй общий заголовок гипотезы, preview-рамку, серый canvas, TEST, Generated, watermark, debug-рамки, подписи агента, внешние ссылки или JS.\n\n"
            f"previous_output:\n{json.dumps(previous_output, ensure_ascii=False, indent=2)}"
        )
        request_json = {
            "model": "openclaw/html_mockup_builder",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "text", "text": "Control mockup reference:"},
                        self._image_content(payload),
                    ],
                }
            ],
            "temperature": 0.1,
            "tools": [],
            "tool_choice": "none",
        }
        logger.info(
            "Sending HTML mockup repair request experiment_id=%s step=%s prompt_chars=%s",
            payload.get("experiment_id"),
            step,
            len(prompt),
        )
        response = await client.post(url, json=request_json, headers=headers)
        logger.info(
            "HTML mockup repair response experiment_id=%s step=%s status=%s bytes=%s",
            payload.get("experiment_id"),
            step,
            response.status_code,
            len(response.content or b""),
        )
        response.raise_for_status()
        response_payload = response.json()
        debug_path = get_settings().storage_dir / str(payload.get("experiment_id")) / f"{step}_raw_html_response.json"
        debug_path.write_text(json.dumps(response_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        repaired = self._extract_image_step_json(response_payload)
        repaired.setdefault("ready_for_generation", True)
        return repaired

    def _render_step_prompt(
        self,
        *,
        payload: dict[str, Any],
        step: str,
        instructions: str,
        context: dict[str, Any],
    ) -> str:
        viewport_width, viewport_height = self._control_image_dimensions(payload)
        base_context = {
            "goal": payload.get("conversion_goal") or "",
            "audience": payload.get("target_audience") or "",
            "viewport_width": viewport_width,
            "viewport_height": viewport_height,
            "control_mockup": (
                "Контрольный макет приложен к этому сообщению как image_url "
                f"({payload['control_image']['mime_type']}). Не ищи файл по имени в workspace."
            ),
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
            "- Не вызывай tools/functions, image tools или file tools. Анализируй приложенные image_url напрямую.\n"
            "- Не ищи локальные файлы в /home/node/.openclaw/workspace и не трактуй MIME type как путь к файлу.\n"
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
        return {
            "agent": "openclaw_pipeline",
            "status": "hypotheses_ready",
            "hypotheses": hypotheses[:3],
            "variant_direction": {},
            "next_step": "user_selects_top_hypothesis",
            "pipeline": {
                "product_manager": pm_output,
                "ux_designer": ux_designer_output,
                "ux_researcher": ux_researcher_output,
                "hypothesis_scorer": scorer_output,
                "next_stage": "user_selects_top_hypothesis",
            },
        }

    @staticmethod
    def _image_data_url(*, mime_type: str, data_base64: str) -> str:
        return f"data:{mime_type};base64,{data_base64}"

    @staticmethod
    def _image_suffix(mime_type: str) -> str:
        if mime_type == "image/png":
            return ".png"
        if mime_type in {"image/jpeg", "image/jpg"}:
            return ".jpg"
        if mime_type == "image/webp":
            return ".webp"
        return ".png"

    @staticmethod
    def _strip_render_payload(payload: dict[str, Any]) -> dict[str, Any]:
        stripped = dict(payload)
        for key in ("control_html", "variant_html"):
            if key in stripped:
                stripped[key] = "[omitted]"
        return stripped

    def _ensure_locked_background_html(
        self,
        *,
        html: str,
        mockup_output: dict[str, Any],
        payload: dict[str, Any],
    ) -> str:
        data_url = self._control_image_data_url(payload)
        overlay_html = mockup_output.get("overlay_html")
        if isinstance(overlay_html, str) and overlay_html.strip():
            logger.info(
                "Building locked-background HTML from overlay_html experiment_id=%s",
                payload.get("experiment_id"),
            )
            return self._build_locked_background_html(
                overlay_html=self._extract_body_inner_html(overlay_html),
                control_image_data_url=data_url,
            )
        if "__CONTROL_IMAGE_DATA_URL__" in html:
            return html.replace("__CONTROL_IMAGE_DATA_URL__", data_url)
        if "control-base" in html and "src=\"data:" in html:
            return html

        logger.warning(
            "HTML mockup ignored locked-background contract; falling back to unchanged control image experiment_id=%s keys=%s",
            payload.get("experiment_id"),
            sorted(mockup_output.keys()),
        )
        return self._build_locked_background_html(
            overlay_html="",
            control_image_data_url=data_url,
        )

    @staticmethod
    def _build_locked_background_html(*, overlay_html: str, control_image_data_url: str) -> str:
        return (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<style>"
            "html,body{margin:0;width:100%;height:100%;overflow:hidden;}"
            "*,*::before,*::after{box-sizing:border-box;}"
            ".simab-variant-root{position:relative;width:100vw;height:100vh;overflow:hidden;background:#fff;}"
            ".control-base{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;object-position:top left;z-index:0;}"
            ".overlay-layer{position:absolute;inset:0;z-index:2;pointer-events:none;}"
            "</style></head><body>"
            "<div class=\"simab-variant-root\">"
            f"<img class=\"control-base\" src=\"{control_image_data_url}\" alt=\"\">"
            f"<div class=\"overlay-layer\">{overlay_html}</div>"
            "</div></body></html>"
        )

    @staticmethod
    def _extract_body_inner_html(html: str) -> str:
        match = re.search(r"<body[^>]*>(.*?)</body>", html, flags=re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return html.strip()

    @staticmethod
    def _control_image_data_url(payload: dict[str, Any]) -> str:
        return (
            f"data:{payload['control_image']['mime_type']};base64,"
            f"{payload['control_image']['data_base64']}"
        )

    async def _render_html_to_png(
        self,
        *,
        html: str,
        payload: dict[str, Any],
        step: str,
    ) -> dict[str, str]:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError("Playwright is required to render HTML mockups") from exc

        experiment_dir = get_settings().storage_dir / str(payload.get("experiment_id"))
        experiment_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = experiment_dir / f"{step}.png"
        viewport_width, viewport_height = self._control_image_dimensions(payload)
        guarded_html = self._inject_viewport_guard(html, viewport_width, viewport_height)
        async with async_playwright() as playwright:
            chromium_path = Path("/usr/bin/chromium")
            launch_kwargs: dict[str, Any] = {"args": ["--no-sandbox"]}
            if chromium_path.exists():
                launch_kwargs["executable_path"] = str(chromium_path)
            browser = await playwright.chromium.launch(**launch_kwargs)
            page = await browser.new_page(
                viewport={"width": viewport_width, "height": viewport_height},
                device_scale_factor=1,
            )
            await page.set_content(guarded_html, wait_until="networkidle")
            await page.screenshot(path=str(screenshot_path), full_page=False)
            await browser.close()
        image_bytes = screenshot_path.read_bytes()
        logger.info(
            "Rendered HTML mockup screenshot experiment_id=%s step=%s path=%s viewport=%sx%s bytes=%s",
            payload.get("experiment_id"),
            step,
            screenshot_path,
            viewport_width,
            viewport_height,
            len(image_bytes),
        )
        return {
            "path": str(screenshot_path),
            "data_base64": base64.b64encode(image_bytes).decode("ascii"),
        }

    @staticmethod
    def _control_image_dimensions(payload: dict[str, Any]) -> tuple[int, int]:
        try:
            image_bytes = base64.b64decode(payload["control_image"]["data_base64"])
        except Exception:
            return 1440, 960

        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") and len(image_bytes) >= 24:
            width = int.from_bytes(image_bytes[16:20], "big")
            height = int.from_bytes(image_bytes[20:24], "big")
            return OpenClawVariantGenerator._clamp_viewport(width, height)

        if image_bytes.startswith(b"\xff\xd8"):
            index = 2
            while index + 9 < len(image_bytes):
                if image_bytes[index] != 0xFF:
                    index += 1
                    continue
                marker = image_bytes[index + 1]
                index += 2
                if marker in {0xD8, 0xD9}:
                    continue
                if index + 2 > len(image_bytes):
                    break
                segment_length = int.from_bytes(image_bytes[index:index + 2], "big")
                if segment_length < 2:
                    break
                if marker in {
                    0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                    0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
                } and index + 7 <= len(image_bytes):
                    height = int.from_bytes(image_bytes[index + 3:index + 5], "big")
                    width = int.from_bytes(image_bytes[index + 5:index + 7], "big")
                    return OpenClawVariantGenerator._clamp_viewport(width, height)
                index += segment_length

        return 1440, 960

    @staticmethod
    def _clamp_viewport(width: int, height: int) -> tuple[int, int]:
        width = max(320, min(int(width or 1440), 2400))
        height = max(320, min(int(height or 960), 2400))
        return width, height

    @staticmethod
    def _inject_viewport_guard(html: str, width: int, height: int) -> str:
        guard = (
            "<style id=\"simab-render-viewport-guard\">"
            "*,*::before,*::after{box-sizing:border-box;}"
            f"html,body{{margin:0!important;width:{width}px!important;min-width:{width}px!important;"
            f"height:{height}px!important;min-height:{height}px!important;overflow:hidden!important;}}"
            "body{position:relative!important;}"
            "</style>"
        )
        if "</head>" in html.lower():
            return re.sub(r"</head>", guard + "</head>", html, count=1, flags=re.IGNORECASE)
        return (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            f"{guard}</head><body>{html}</body></html>"
        )

    def _extract_variant_html(self, mockup_output: dict[str, Any]) -> str:
        for key in ("variant_html", "html", "mockup_html"):
            value = mockup_output.get(key)
            if isinstance(value, str) and value.strip():
                return self._normalize_html_document(value)
        variant = mockup_output.get("variant")
        if isinstance(variant, dict):
            for key in ("html", "variant_html"):
                value = variant.get(key)
                if isinstance(value, str) and value.strip():
                    return self._normalize_html_document(value)
        raise ValueError("HTML mockup generator returned no variant_html")

    @staticmethod
    def _normalize_html_document(html: str) -> str:
        stripped = html.strip()
        fenced = re.search(r"```(?:html)?\s*(.*?)```", stripped, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            stripped = fenced.group(1).strip()
        if "<html" not in stripped.lower():
            stripped = (
                "<!doctype html><html><head><meta charset=\"utf-8\">"
                "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
                "</head><body>"
                f"{stripped}"
                "</body></html>"
            )
        return stripped

    def _extract_image_step_json(self, response_payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._parse_gateway_payload(response_payload)
        except Exception:
            message = self._message_payload(response_payload)
            content = message.get("content")
            if isinstance(content, list):
                text_parts = [
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict) and isinstance(part.get("text"), str)
                ]
                if text_parts:
                    return self._parse_json_text("\n".join(text_parts))
            if isinstance(content, str) and content.strip():
                return self._parse_json_text(content)
        return {}

    @staticmethod
    def _message_payload(response_payload: dict[str, Any]) -> dict[str, Any]:
        try:
            message = response_payload["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("OpenAI-compatible response has no choices[0].message") from exc
        if not isinstance(message, dict):
            raise ValueError("OpenAI-compatible message must be an object")
        return message

    @staticmethod
    def _parse_json_text(text: str) -> dict[str, Any]:
        stripped = text.strip()
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
            raise ValueError("JSON content must be an object")
        return result

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
