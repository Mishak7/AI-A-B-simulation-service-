from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from app.config import get_settings


class PromptRenderer:
    def __init__(self, prompt_dir: Path | None = None) -> None:
        self.prompt_dir = prompt_dir or get_settings().prompt_dir
        self.environment = Environment(
            loader=FileSystemLoader(self.prompt_dir),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, template_name: str, context: dict[str, Any]) -> str:
        try:
            template = self.environment.get_template(template_name)
        except TemplateNotFound as exc:
            raise FileNotFoundError(f"Prompt template not found: {template_name}") from exc
        return template.render(**context)
