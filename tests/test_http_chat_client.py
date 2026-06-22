import asyncio
import json

import httpx
import pytest

import app.llm.http_chat_client as chat_module
from app.config import Settings
from app.llm.http_chat_client import ChatServiceUnavailableError, HTTPChatClient


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
