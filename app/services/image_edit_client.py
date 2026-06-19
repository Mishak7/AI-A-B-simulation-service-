import base64
import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

CHAT_RESPONSE_ERROR = (
    "Image generation endpoint returned chat-completions response shape. "
    "Expected image response data[0].b64_json or data[0].url."
)
UNKNOWN_RESPONSE_ERROR = (
    "Image generation endpoint returned an unknown response shape. "
    "Expected image response data[0].b64_json or data[0].url."
)


@dataclass(frozen=True)
class ImageEditResult:
    output_path: Path
    mime_type: str
    size: str
    source_width: int | None
    source_height: int | None
    response_shape: str
    input_fidelity_used: bool
    provider_metadata: dict[str, Any]


class ImageEditClient:
    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._http_client = http_client

    async def edit(
        self,
        *,
        control_image_path: Path,
        prompt: str,
        output_dir: Path,
    ) -> ImageEditResult:
        api_key = self.settings.effective_image_api_key
        if not api_key:
            raise ValueError("SAB_IMAGE_API_KEY (or SAB_REAL_API_KEY) is required")

        dimensions = self.source_image_dimensions(control_image_path)
        configured_size = (
            self.settings.image_size
            if self.settings.image_size_is_explicit
            else None
        )
        size = self.select_size(
            width=dimensions[0],
            height=dimensions[1],
            configured_size=configured_size,
        )
        endpoint_url = (
            self.settings.image_base_url.rstrip("/")
            + self.settings.image_edit_endpoint_path
        )
        data = {
            "model": self.settings.image_model,
            "prompt": prompt,
            "size": size,
            "quality": self.settings.image_quality,
        }
        if self.settings.image_input_fidelity:
            data["input_fidelity"] = self.settings.image_input_fidelity

        logger.info(
            "Sending image edit endpoint=%s model=%s size=%s quality=%s "
            "input_fidelity=%s source_dimensions=%sx%s",
            endpoint_url,
            self.settings.image_model,
            size,
            self.settings.image_quality,
            bool(self.settings.image_input_fidelity),
            dimensions[0],
            dimensions[1],
        )

        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(
            timeout=self.settings.image_timeout_seconds,
            follow_redirects=True,
        )
        try:
            with control_image_path.open("rb") as image_file:
                response = await client.post(
                    endpoint_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    data=data,
                    files={
                        "image": (
                            control_image_path.name,
                            image_file,
                            mimetypes.guess_type(control_image_path.name)[0]
                            or "application/octet-stream",
                        )
                    },
                )
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError as exc:
                raise ValueError(UNKNOWN_RESPONSE_ERROR) from exc
            if not isinstance(payload, dict):
                raise ValueError(UNKNOWN_RESPONSE_ERROR)
            response_shape, image_bytes, image_url = self.parse_image_response(payload)
            logger.info("Image edit response shape=%s", response_shape)

            response_mime: str | None = None
            if image_url:
                self._validate_download_url(image_url)
                download = await client.get(image_url)
                download.raise_for_status()
                image_bytes = download.content
                response_mime = download.headers.get("content-type", "").split(";", 1)[0]
                if len(image_bytes) > self.settings.image_max_download_bytes:
                    raise ValueError("Generated image download exceeds the configured size limit")

            if image_bytes is None:
                raise ValueError(UNKNOWN_RESPONSE_ERROR)
            mime_type = self.detect_image_mime(image_bytes, response_mime)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"challenger{self.image_suffix(mime_type)}"
            output_path.write_bytes(image_bytes)
            metadata = self.safe_provider_metadata(payload)
            logger.info("Generated image saved path=%s bytes=%s", output_path, len(image_bytes))
            return ImageEditResult(
                output_path=output_path,
                mime_type=mime_type,
                size=size,
                source_width=dimensions[0],
                source_height=dimensions[1],
                response_shape=response_shape,
                input_fidelity_used=bool(self.settings.image_input_fidelity),
                provider_metadata=metadata,
            )
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def parse_image_response(
        payload: dict[str, Any],
    ) -> tuple[str, bytes | None, str | None]:
        if "choices" in payload:
            raise ValueError(CHAT_RESPONSE_ERROR)
        data = payload.get("data")
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise ValueError(UNKNOWN_RESPONSE_ERROR)
        item = data[0]
        encoded = item.get("b64_json")
        if isinstance(encoded, str) and encoded:
            try:
                return "b64_json", base64.b64decode(encoded, validate=True), None
            except ValueError as exc:
                raise ValueError("Image response contains invalid data[0].b64_json") from exc
        url = item.get("url")
        if isinstance(url, str) and url:
            return "url", None, url
        raise ValueError(UNKNOWN_RESPONSE_ERROR)

    @staticmethod
    def select_size(
        *, width: int | None, height: int | None, configured_size: str | None
    ) -> str:
        if configured_size:
            return configured_size
        if not width or not height:
            return "1536x1024"
        ratio = width / height
        if ratio > 1.15:
            return "1536x1024"
        if ratio < 1 / 1.15:
            return "1024x1536"
        return "1024x1024"

    @staticmethod
    def source_image_dimensions(path: Path) -> tuple[int | None, int | None]:
        data = path.read_bytes()
        if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
            return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        if data.startswith(b"\xff\xd8"):
            index = 2
            while index + 9 < len(data):
                if data[index] != 0xFF:
                    index += 1
                    continue
                marker = data[index + 1]
                index += 2
                if index + 2 > len(data):
                    break
                length = int.from_bytes(data[index : index + 2], "big")
                if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF} and index + 7 <= len(data):
                    return (
                        int.from_bytes(data[index + 5 : index + 7], "big"),
                        int.from_bytes(data[index + 3 : index + 5], "big"),
                    )
                if length < 2:
                    break
                index += length
        return None, None

    @staticmethod
    def detect_image_mime(image_bytes: bytes, response_mime: str | None = None) -> str:
        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if image_bytes.startswith(b"\xff\xd8"):
            return "image/jpeg"
        if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
            return "image/webp"
        if response_mime in {"image/png", "image/jpeg", "image/webp"}:
            return response_mime
        return "image/png"

    @staticmethod
    def image_suffix(mime_type: str) -> str:
        return {"image/jpeg": ".jpg", "image/webp": ".webp"}.get(mime_type, ".png")

    @staticmethod
    def safe_provider_metadata(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            key: payload[key]
            for key in ("id", "created", "background", "output_format", "quality", "size", "usage")
            if key in payload
        }

    @staticmethod
    def _validate_download_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Image response URL must use http or https")
