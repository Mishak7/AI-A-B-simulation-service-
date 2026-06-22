import asyncio
import base64
import re
from pathlib import Path

import httpx
import pytest

from app.config import Settings, get_settings
from app.models import Experiment
from app.services.image_edit_client import (
    CHAT_RESPONSE_ERROR,
    UNKNOWN_RESPONSE_ERROR,
    ImageEditClient,
    ImageEditResult,
)
from app.services.llm_variant_generator import LLMVariantGenerator


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x02\x00\x00\x00\x01"
)


def make_settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        image_api_key="test-key",
        image_base_url="https://images.example/v1/",
        **overrides,
    )


def test_image_edit_sends_multipart_to_configured_endpoint(tmp_path: Path) -> None:
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["content_type"] = request.headers["content-type"]
        captured["body"] = await request.aread()
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(PNG_BYTES).decode()}]},
        )

    control = tmp_path / "control.png"
    control.write_bytes(PNG_BYTES)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = make_settings(
        image_edit_endpoint_path="/custom/images/edit",
        image_size="1536x1024",
        image_quality="high",
        image_input_fidelity="high",
    )
    try:
        result = asyncio.run(
            ImageEditClient(settings, client).edit(
                control_image_path=control,
                prompt="Change only the CTA wording",
                output_dir=tmp_path / "out",
            )
        )
    finally:
        asyncio.run(client.aclose())

    body = captured["body"]
    assert captured["url"] == "https://images.example/v1/custom/images/edit"
    assert captured["content_type"].startswith("multipart/form-data; boundary=")
    for field in (
        b'name="model"',
        b'name="prompt"',
        b'name="image"',
        b'name="size"',
        b'name="quality"',
        b'name="input_fidelity"',
    ):
        assert field in body
    assert settings.image_model.encode() in body
    assert b"Change only the CTA wording" in body
    assert b"1536x1024" in body
    assert b"high" in body
    assert b'name="messages"' not in body
    assert b'name="tools"' not in body
    assert b'name="tool_choice"' not in body
    assert result.output_path.read_bytes() == PNG_BYTES
    assert result.response_shape == "b64_json"


def test_image_response_parser_handles_base64() -> None:
    shape, image_bytes, url = ImageEditClient.parse_image_response(
        {"data": [{"b64_json": base64.b64encode(b"image").decode()}]}
    )
    assert (shape, image_bytes, url) == ("b64_json", b"image", None)


def test_image_edit_downloads_url_response(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"data": [{"url": "https://cdn.example/result.png"}]})
        return httpx.Response(200, content=PNG_BYTES, headers={"content-type": "image/png"})

    control = tmp_path / "control.png"
    control.write_bytes(PNG_BYTES)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = asyncio.run(
            ImageEditClient(make_settings(), client).edit(
                control_image_path=control,
                prompt="Local change",
                output_dir=tmp_path / "out",
            )
        )
    finally:
        asyncio.run(client.aclose())
    assert result.response_shape == "url"
    assert result.output_path.read_bytes() == PNG_BYTES


def test_image_response_rejects_chat_completion_shape() -> None:
    with pytest.raises(ValueError, match=re.escape(CHAT_RESPONSE_ERROR)):
        ImageEditClient.parse_image_response(
            {"choices": [{"message": {"content": "not an image"}}]}
        )


def test_image_response_rejects_unknown_shape() -> None:
    with pytest.raises(ValueError, match=re.escape(UNKNOWN_RESPONSE_ERROR)):
        ImageEditClient.parse_image_response({"data": [{}]})


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        (1600, 900, "1536x1024"),
        (900, 1600, "1024x1536"),
        (1000, 1000, "1024x1024"),
    ],
)
def test_automatic_size_selection(width: int, height: int, expected: str) -> None:
    assert ImageEditClient.select_size(
        width=width, height=height, configured_size=None
    ) == expected


def test_explicit_size_override_wins() -> None:
    assert ImageEditClient.select_size(
        width=900, height=1600, configured_size="1536x1024"
    ) == "1536x1024"


@pytest.mark.parametrize(
    ("explicit", "hypothesis", "expected"),
    [
        ("explicit prompt", {"generation_prompt": "nested"}, "explicit prompt"),
        (None, {"generation_prompt": "nested"}, "nested"),
        (None, {"proposed_change": "proposal"}, "proposal"),
        (None, {"hypothesis": "hypothesis text"}, "hypothesis text"),
        (None, {}, "Apply the selected A/B hypothesis"),
    ],
)
def test_image_prompt_fallback_order(explicit, hypothesis, expected) -> None:
    prompt = LLMVariantGenerator._build_image_prompt(
        selected_hypothesis=hypothesis,
        generation_prompt=explicit,
    )
    assert expected in prompt


def test_image_prompt_has_preservation_rules_and_no_raw_hypothesis_json() -> None:
    hypothesis = {
        "title": "Test",
        "generation_prompt": "Replace the hero visual",
        "rationale": "SECRET_SCORER_METADATA",
        "score": 99,
    }
    prompt = LLMVariantGenerator._build_image_prompt(
        selected_hypothesis=hypothesis,
        generation_prompt=None,
    )
    assert "Replace the hero visual" in prompt
    assert "SECRET_SCORER_METADATA" not in prompt
    assert '"score": 99' not in prompt
    for instruction in ("Make exactly this change", "Keep everything else unchanged"):
        assert instruction in prompt
    assert len(prompt) < 500


@pytest.mark.parametrize(
    "change",
    [
        "change CTA wording",
        "replace hero visual",
        "emphasize cashback",
        "add urgency to the main offer",
        "simplify onboarding copy",
        "promote salary transfer",
        "highlight free delivery",
    ],
)
def test_image_prompt_is_generic_for_arbitrary_hypotheses(change: str) -> None:
    prompt = LLMVariantGenerator._build_image_prompt(
        selected_hypothesis={"proposed_change": change},
        generation_prompt=None,
    )
    assert change in prompt


def test_selected_hypothesis_always_calls_images_edit_client(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    control = tmp_path / "control.png"
    control.write_bytes(PNG_BYTES)
    monkeypatch.setenv("SAB_STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    captured = {}

    async def fake_edit(self, *, control_image_path, prompt, output_dir):
        captured["control_image_path"] = control_image_path
        captured["prompt"] = prompt
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "challenger.png"
        output_path.write_bytes(PNG_BYTES)
        return ImageEditResult(
            output_path=output_path,
            mime_type="image/png",
            size="1536x1024",
            source_width=2,
            source_height=1,
            response_shape="b64_json",
            input_fidelity_used=True,
            provider_metadata={},
        )

    monkeypatch.setattr(ImageEditClient, "edit", fake_edit)
    caplog.set_level("INFO")
    experiment = Experiment(
        id=42,
        name="Direct edit",
        conversion_goal="",
        target_audience="",
        control_image_path=str(control),
    )
    try:
        result = asyncio.run(
            LLMVariantGenerator().generate_variant_image(
                experiment=experiment,
                selected_hypothesis={
                    "title": "CTA",
                    "generation_prompt": "Change the CTA text to Continue",
                },
            )
        )
    finally:
        get_settings.cache_clear()

    assert captured["control_image_path"] == control
    assert "Change the CTA text to Continue" in captured["prompt"]
    assert result["runtime"] == "images_edit"
    assert "Calling image edit model" in caplog.text
    assert "Image edit model completed" in caplog.text
