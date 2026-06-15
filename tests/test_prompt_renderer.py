from pathlib import Path

from app.services.prompt_renderer import PromptRenderer


def test_prompt_renderer_reads_template_from_disk(tmp_path: Path) -> None:
    template = tmp_path / "example.md"
    template.write_text("Goal: {{ conversion_goal }}", encoding="utf-8")

    renderer = PromptRenderer(prompt_dir=tmp_path)

    assert renderer.render("example.md", {"conversion_goal": "Signup"}) == "Goal: Signup"


def test_prompt_renderer_supports_arbitrary_context_variables(tmp_path: Path) -> None:
    template = tmp_path / "custom.md"
    template.write_text(
        "Retrieved: {{ retrieved_context }} | Metadata: {{ experiment_metadata.owner }}",
        encoding="utf-8",
    )

    renderer = PromptRenderer(prompt_dir=tmp_path)
    rendered = renderer.render(
        "custom.md",
        {
            "retrieved_context": "pricing-page notes",
            "experiment_metadata": {"owner": "growth"},
        },
    )

    assert rendered == "Retrieved: pricing-page notes | Metadata: growth"


def test_prompt_renderer_missing_variables_render_empty(tmp_path: Path) -> None:
    template = tmp_path / "optional.md"
    template.write_text("Optional: {{ future_variable }}", encoding="utf-8")

    renderer = PromptRenderer(prompt_dir=tmp_path)

    assert renderer.render("optional.md", {}) == "Optional: "


def test_persona_simulation_prompt_uses_neutral_image_labels() -> None:
    renderer = PromptRenderer()

    rendered = renderer.render(
        "persona_simulation.md",
        {
            "persona_profile": {"name": "Test"},
            "conversion_goal": "Click CTA",
            "target_audience": "Audience",
            "image_1_visual_quality": "pass",
            "image_1_visual_issues": "None",
            "image_2_visual_quality": "pass",
            "image_2_visual_issues": "None",
            "experiment_context": {},
        },
    )

    assert "Control" not in rendered
    assert "Challenger" not in rendered
    assert "presented_order" not in rendered
    assert "Image 1 visual quality" in rendered
    assert "Image 2 visual quality" in rendered
