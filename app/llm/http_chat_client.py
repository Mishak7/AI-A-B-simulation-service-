import asyncio
import logging
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ChatServiceUnavailableError(RuntimeError):
    """The upstream chat service stayed unavailable after all retries."""


class ChatRequestError(RuntimeError):
    """The upstream chat service rejected a non-retryable request."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Chat server returned HTTP {status_code}: {body}")


class HTTPChatClient:
    """Minimal HTTP client for chat-completions-shaped model servers."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        initial_concurrency: int = 2,
        max_concurrency: int = 4,
        increase_after_successes: int = 8,
        min_interval_seconds: float = 0.25,
        max_interval_seconds: float = 2.0,
        max_retry_delay_seconds: float = 60.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.max_concurrency = max(1, max_concurrency)
        self.current_concurrency = min(
            self.max_concurrency, max(1, initial_concurrency)
        )
        self.increase_after_successes = max(1, increase_after_successes)
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self.max_interval_seconds = max(
            self.min_interval_seconds, max_interval_seconds
        )
        self.current_interval_seconds = self.min_interval_seconds
        self.max_retry_delay_seconds = max(1.0, max_retry_delay_seconds)
        self.http_client = http_client
        self._capacity = asyncio.Condition()
        self._inflight = 0
        self._success_streak = 0
        self._adaptive_cooldown_until = 0.0
        self._rate_lock = asyncio.Lock()
        self._next_request_at = 0.0

    async def complete(
        self,
        content: str | list[dict[str, Any]],
        *,
        temperature: float,
        max_tokens: int | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        await self._acquire_capacity()
        try:
            for attempt in range(self.max_retries + 1):
                response: httpx.Response | None = None
                try:
                    await self._wait_for_request_slot()
                    if self.http_client is not None:
                        response = await self.http_client.post(
                            url, headers=headers, json=payload
                        )
                    else:
                        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                            response = await client.post(url, headers=headers, json=payload)
                    if response.status_code == 429 or response.status_code >= 500:
                        response.raise_for_status()
                    if response.is_error:
                        body = response.text[:500]
                        raise ChatRequestError(response.status_code, body)
                    data = response.json()
                    message = data["choices"][0]["message"]["content"]
                    if not message:
                        raise ValueError("Chat server returned empty message content")
                    await self._record_success()
                    return str(message)
                except (
                    httpx.TransportError,
                    httpx.HTTPStatusError,
                ) as exc:
                    status = response.status_code if response is not None else None
                    retry_after = self._retry_after_seconds(response)
                    delay = min(
                        self.max_retry_delay_seconds,
                        max(2**attempt, retry_after or 0.0),
                    )
                    if status == 429:
                        await self._record_throttle(delay)
                    else:
                        await self._defer_requests(delay)
                    if attempt >= self.max_retries:
                        raise ChatServiceUnavailableError(
                            f"Chat service unavailable after {attempt + 1} attempts "
                            f"(status={status})"
                        ) from exc
                    logger.warning(
                        "Chat request failed; retrying model=%s status=%s attempt=%s/%s "
                        "delay_seconds=%.1f error=%s",
                        self.model,
                        status,
                        attempt + 1,
                        self.max_retries + 1,
                        delay,
                        exc.__class__.__name__,
                    )
                    await asyncio.sleep(delay)
        finally:
            await self._release_capacity()

        raise RuntimeError("Chat request retry loop exited unexpectedly")

    async def _wait_for_request_slot(self) -> None:
        async with self._rate_lock:
            delay = max(0.0, self._next_request_at - time.monotonic())
            if delay:
                await asyncio.sleep(delay)
            self._next_request_at = (
                time.monotonic() + self.current_interval_seconds
            )

    async def _acquire_capacity(self) -> None:
        async with self._capacity:
            await self._capacity.wait_for(
                lambda: self._inflight < self.current_concurrency
            )
            self._inflight += 1

    async def _release_capacity(self) -> None:
        async with self._capacity:
            self._inflight -= 1
            self._capacity.notify_all()

    async def _record_success(self) -> None:
        async with self._capacity:
            if time.monotonic() < self._adaptive_cooldown_until:
                self._success_streak = 0
                return
            self._success_streak += 1
            if self._success_streak >= self.increase_after_successes:
                if self.current_concurrency < self.max_concurrency:
                    self.current_concurrency += 1
                self.current_interval_seconds = max(
                    self.min_interval_seconds,
                    self.current_interval_seconds * 0.8,
                )
                self._success_streak = 0
                logger.info(
                    "Adaptive Qwen limiter increased concurrency=%s interval_seconds=%.2f",
                    self.current_concurrency,
                    self.current_interval_seconds,
                )
                self._capacity.notify_all()

    async def _record_throttle(self, delay: float) -> None:
        async with self._capacity:
            previous = self.current_concurrency
            self.current_concurrency = max(1, self.current_concurrency // 2)
            self.current_interval_seconds = min(
                self.max_interval_seconds,
                max(
                    self.min_interval_seconds,
                    self.current_interval_seconds * 2,
                ),
            )
            self._success_streak = 0
            self._adaptive_cooldown_until = max(
                self._adaptive_cooldown_until,
                time.monotonic() + delay,
            )
            logger.warning(
                "Adaptive Qwen limiter throttled concurrency=%s->%s interval_seconds=%.2f",
                previous,
                self.current_concurrency,
                self.current_interval_seconds,
            )
            self._capacity.notify_all()
        await self._defer_requests(delay)

    async def _defer_requests(self, delay: float) -> None:
        async with self._rate_lock:
            self._next_request_at = max(
                self._next_request_at,
                time.monotonic() + max(0.0, delay),
            )

    @staticmethod
    def _retry_after_seconds(response: httpx.Response | None) -> float | None:
        if response is None or response.status_code != 429:
            return None
        value = response.headers.get("Retry-After")
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                return None
