import asyncio
import base64
import io
import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

import app.llm.http_chat_client as chat_module
from app.config import Settings
from app.llm.http_chat_client import (
    ChatRequestError,
    ChatServiceUnavailableError,
    HTTPChatClient,
)
from app.llm.real_client import RealLLMClient


def test_qwen_and_image_credentials_are_independent() -> None:
    settings = Settings(qwen_api_key="qwen-key", real_api_key="image-fallback-key")

    assert settings.qwen_api_key == "qwen-key"
    assert settings.effective_image_api_key == "image-fallback-key"


def test_http_chat_client_sends_qwen_multimodal_payload() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Red", "reasoning_content": "..."}}
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async_client = httpx.AsyncClient(transport=transport)
    client = HTTPChatClient(
        api_key="secret",
        base_url="https://45.9.24.84/v1",
        model="Qwen3.5-397B-A17B-FP8",
        timeout_seconds=60,
        max_retries=0,
        http_client=async_client,
    )
    content = [
        {"type": "text", "text": "What color is this image?"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,AA=="},
        },
    ]

    result = asyncio.run(client.complete(content, temperature=0))
    asyncio.run(async_client.aclose())

    assert result == "Red"
    assert captured["url"] == "https://45.9.24.84/v1/chat/completions"
    assert captured["authorization"] == "Bearer secret"
    assert captured["payload"]["model"] == "Qwen3.5-397B-A17B-FP8"
    assert captured["payload"]["messages"][0]["content"] == content


def test_http_chat_client_retries_429_using_retry_after(monkeypatch) -> None:
    attempts = 0
    sleeps = []
    clock = [0.0]

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr(chat_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(chat_module.time, "monotonic", lambda: clock[0])
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = HTTPChatClient(
        api_key="secret",
        base_url="https://45.9.24.84/v1",
        model="Qwen3.5-397B-A17B-FP8",
        timeout_seconds=60,
        max_retries=2,
        min_interval_seconds=0,
        http_client=async_client,
    )

    result = asyncio.run(client.complete("test", temperature=0))
    asyncio.run(async_client.aclose())

    assert result == "ok"
    assert attempts == 2
    assert sleeps == [3.0]


def test_http_chat_client_wraps_exhausted_429() -> None:
    async_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(429))
    )
    client = HTTPChatClient(
        api_key="secret",
        base_url="https://45.9.24.84/v1",
        model="Qwen3.5-397B-A17B-FP8",
        timeout_seconds=60,
        max_retries=0,
        min_interval_seconds=0,
        http_client=async_client,
    )

    with pytest.raises(ChatServiceUnavailableError, match="status=429"):
        asyncio.run(client.complete("test", temperature=0))
    asyncio.run(async_client.aclose())


def test_http_chat_client_exposes_non_retryable_400() -> None:
    async_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(400, text="Bad Request")
        )
    )
    client = HTTPChatClient(
        api_key="secret",
        base_url="https://example.test/v1",
        model="vision-model",
        timeout_seconds=60,
        max_retries=0,
        min_interval_seconds=0,
        http_client=async_client,
    )

    with pytest.raises(ChatRequestError, match="HTTP 400") as error:
        asyncio.run(client.complete("test", temperature=0))
    asyncio.run(async_client.aclose())

    assert error.value.status_code == 400


def test_real_client_compacts_large_image_for_visual_calls(tmp_path: Path) -> None:
    source = tmp_path / "large.png"
    Image.new("RGBA", (3006, 1592), (20, 80, 140, 255)).save(source)
    original = source.read_bytes()

    content = RealLLMClient._image_content_part(str(source))
    data_url = content["image_url"]["url"]
    header, encoded = data_url.split(",", 1)
    prepared = base64.b64decode(encoded)

    assert header == "data:image/jpeg;base64"
    assert len(prepared) <= 700_000
    with Image.open(io.BytesIO(prepared)) as image:
        assert max(image.size) <= 1600
    assert source.read_bytes() == original


def test_http_chat_client_retries_remote_protocol_disconnect(monkeypatch) -> None:
    attempts = 0
    sleeps = []
    clock = [0.0]

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.RemoteProtocolError(
                "Server disconnected without sending a response",
                request=request,
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr(chat_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(chat_module.time, "monotonic", lambda: clock[0])
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = HTTPChatClient(
        api_key="secret",
        base_url="https://45.9.24.84/v1",
        model="Qwen3.5-397B-A17B-FP8",
        timeout_seconds=60,
        max_retries=2,
        min_interval_seconds=0,
        http_client=async_client,
    )

    result = asyncio.run(client.complete("test", temperature=0))
    asyncio.run(async_client.aclose())

    assert result == "ok"
    assert attempts == 2
    assert sleeps == [1.0]


def test_adaptive_limiter_increases_on_success_and_halves_on_429() -> None:
    client = HTTPChatClient(
        api_key="secret",
        base_url="https://45.9.24.84/v1",
        model="Qwen3.5-397B-A17B-FP8",
        timeout_seconds=60,
        max_retries=0,
        initial_concurrency=2,
        max_concurrency=4,
        increase_after_successes=2,
        min_interval_seconds=0.25,
        max_interval_seconds=2.0,
    )

    async def scenario() -> None:
        await client._record_success()
        await client._record_success()
        assert client.current_concurrency == 3

        await client._record_success()
        await client._record_success()
        assert client.current_concurrency == 4

        await client._record_throttle(3)
        assert client.current_concurrency == 2
        assert client.current_interval_seconds == 0.5

    asyncio.run(scenario())
