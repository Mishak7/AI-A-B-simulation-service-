import asyncio

import pytest

from app.services.llm_variant_generator import LLMVariantGenerator


def completion_payload(content):
    return {"choices": [{"message": {"content": content}}]}


def test_pipeline_step_calls_configured_model_directly(monkeypatch) -> None:
    captured = {}

    class Response:
        def model_dump(self):
            return completion_payload('{"role":"product_manager"}')

    class Completions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return Response()

    class Client:
        chat = type("Chat", (), {"completions": Completions()})()

    monkeypatch.setenv("SAB_AGENT_PIPELINE_MODEL", "openai/gpt-4.1-mini")
    monkeypatch.setenv("SAB_AGENT_PIPELINE_MAX_TOKENS", "8192")
    from app.config import get_settings

    get_settings.cache_clear()
    payload = {
        "name": "Test",
        "conversion_goal": "Goal",
        "target_audience": "Audience",
        "control_image": {"mime_type": "image/png", "data_base64": "AA=="},
    }
    result = asyncio.run(
        LLMVariantGenerator()._call_pipeline_step(
            Client(), payload, "product_manager", "Return JSON", {}, True
        )
    )

    assert result == {"role": "product_manager"}
    assert captured["model"] == "openai/gpt-4.1-mini"
    assert captured["max_tokens"] == 8192
    assert captured["messages"][0]["content"][1]["type"] == "image_url"
    get_settings.cache_clear()


def test_parser_accepts_plain_json_object() -> None:
    assert LLMVariantGenerator._parse_chat_completion_payload(
        completion_payload('{"status":"ok"}')
    ) == {"status": "ok"}


def test_parser_ignores_second_json_object() -> None:
    content = (
        '{"top_hypotheses":[{"title":"First"}]}\n'
        '{"debug":"second object must not break parsing"}'
    )
    assert LLMVariantGenerator._parse_chat_completion_payload(
        completion_payload(content)
    ) == {"top_hypotheses": [{"title": "First"}]}


def test_scorer_parser_skips_skill_creation_proposal_and_selects_result() -> None:
    content = (
        '{"action":"create","name":"hypothesis_scorer","proposal_content":"..."}\n'
        '{"scored_hypotheses":[],"top_hypotheses":[{"title":"Real result"}]}'
    )
    assert LLMVariantGenerator._parse_chat_completion_payload(
        completion_payload(content),
        expected_keys={"top_hypotheses", "scored_hypotheses"},
    ) == {
        "scored_hypotheses": [],
        "top_hypotheses": [{"title": "Real result"}],
    }


def test_scorer_parser_rejects_only_skill_creation_proposal() -> None:
    with pytest.raises(ValueError, match="expected JSON keys"):
        LLMVariantGenerator._parse_chat_completion_payload(
            completion_payload('{"action":"create","name":"hypothesis_scorer"}'),
            expected_keys={"top_hypotheses", "scored_hypotheses"},
        )


def test_parser_accepts_fenced_json_with_explanation_after_fence() -> None:
    content = '```json\n{"status":"ok"}\n```\nAdditional explanation.'
    assert LLMVariantGenerator._parse_chat_completion_payload(
        completion_payload(content)
    ) == {"status": "ok"}


def test_parser_finds_json_after_prose_and_ignores_trailing_text() -> None:
    content = 'Here is the result:\n{"status":"ok","count":3}\nDone.'
    assert LLMVariantGenerator._parse_chat_completion_payload(
        completion_payload(content)
    ) == {"status": "ok", "count": 3}


def test_parser_supports_chat_content_parts() -> None:
    content = [
        {"type": "text", "text": "Result:"},
        {"type": "text", "text": '{"status":"ok"}'},
    ]
    assert LLMVariantGenerator._parse_chat_completion_payload(
        completion_payload(content)
    ) == {"status": "ok"}


def test_parser_rejects_response_without_json_object() -> None:
    with pytest.raises(ValueError, match="does not contain a valid JSON object"):
        LLMVariantGenerator._parse_chat_completion_payload(
            completion_payload("No structured response")
        )


def test_pipeline_uses_highest_scored_hypotheses_when_top_list_is_missing() -> None:
    result = LLMVariantGenerator._build_pipeline_response(
        pm_output={},
        ux_designer_output={},
        ux_researcher_output={},
        scorer_output={
            "scored_hypotheses": [
                {"title": "Low", "score": 1, "proposed_change": "Low change"},
                {"title": "High", "score": 5, "proposed_change": "High change"},
            ]
        },
    )
    assert [item["title"] for item in result["hypotheses"]] == ["High", "Low"]


def test_pipeline_rejects_empty_scorer_result() -> None:
    with pytest.raises(ValueError, match="returned no usable"):
        LLMVariantGenerator._build_pipeline_response(
            pm_output={},
            ux_designer_output={},
            ux_researcher_output={},
            scorer_output={"top_hypotheses": []},
        )
