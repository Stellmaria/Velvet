from __future__ import annotations

import asyncio
import base64
import binascii
import io
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit

from aiohttp import ClientError, ClientSession, ClientTimeout, web
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger("velvet.vision_gateway")
Image.MAX_IMAGE_PIXELS = 40_000_000

_DATA_PREFIX = "data:"
_ALLOWED_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_ALLOWED_REQUEST_FIELDS = frozenset(
    {
        "model",
        "messages",
        "stream",
        "temperature",
        "top_p",
        "max_tokens",
        "response_format",
        "seed",
        "stop",
        "frequency_penalty",
        "presence_penalty",
    }
)
_ALLOWED_RUNTIME_HOSTS = frozenset({"vision-runtime"})


class GatewayRequestError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GatewaySettings:
    host: str
    port: int
    runtime_base_url: str
    model: str
    expected_digest: str | None
    max_concurrency: int
    max_image_side: int
    max_images: int
    max_decoded_image_bytes: int
    request_timeout_seconds: int
    health_timeout_seconds: int
    client_max_size: int

    @classmethod
    def from_env(cls) -> "GatewaySettings":
        model = os.getenv("VISION_MODEL", "").strip()
        if not model:
            raise RuntimeError("VISION_MODEL must be configured.")
        runtime_base_url = (
            os.getenv("VISION_RUNTIME_BASE_URL", "http://vision-runtime:11434")
            .strip()
            .rstrip("/")
        )
        _validate_runtime_base_url(runtime_base_url)
        return cls(
            host=os.getenv("VISION_GATEWAY_HOST", "0.0.0.0").strip() or "0.0.0.0",
            port=_bounded_int("VISION_GATEWAY_PORT", 8080, 1, 65535),
            runtime_base_url=runtime_base_url,
            model=model,
            expected_digest=os.getenv("VISION_MODEL_EXPECTED_DIGEST", "").strip() or None,
            max_concurrency=_bounded_int("VISION_MAX_CONCURRENCY", 1, 1, 4),
            max_image_side=_bounded_int("VISION_MAX_IMAGE_SIDE", 1280, 256, 4096),
            max_images=_bounded_int("VISION_MAX_IMAGES", 8, 1, 16),
            max_decoded_image_bytes=_bounded_int(
                "VISION_MAX_DECODED_IMAGE_BYTES",
                20 * 1024 * 1024,
                1 * 1024 * 1024,
                100 * 1024 * 1024,
            ),
            request_timeout_seconds=_bounded_int(
                "VISION_REQUEST_TIMEOUT_SECONDS", 300, 10, 1800
            ),
            health_timeout_seconds=_bounded_int(
                "VISION_HEALTH_TIMEOUT_SECONDS", 5, 1, 30
            ),
            client_max_size=_bounded_int(
                "VISION_GATEWAY_MAX_REQUEST_BYTES",
                32 * 1024 * 1024,
                1 * 1024 * 1024,
                128 * 1024 * 1024,
            ),
        )


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer.") from error
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _validate_runtime_base_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "http":
        raise RuntimeError("VISION_RUNTIME_BASE_URL must use internal http://.")
    if parsed.hostname not in _ALLOWED_RUNTIME_HOSTS:
        raise RuntimeError("VISION_RUNTIME_BASE_URL must use Compose host vision-runtime.")
    if parsed.username or parsed.password:
        raise RuntimeError("VISION_RUNTIME_BASE_URL cannot contain credentials.")
    if parsed.query or parsed.fragment:
        raise RuntimeError("VISION_RUNTIME_BASE_URL cannot contain query or fragment.")


def _parse_data_uri(value: str) -> tuple[str, bytes]:
    if not value.startswith(_DATA_PREFIX):
        raise GatewayRequestError("Only base64 data URI images are accepted.")
    header, separator, encoded = value.partition(",")
    if not separator or ";base64" not in header.casefold():
        raise GatewayRequestError("Image data URI must use base64 encoding.")
    mime_type = header[5:].split(";", 1)[0].strip().casefold()
    if mime_type not in _ALLOWED_IMAGE_MIME_TYPES:
        raise GatewayRequestError("Unsupported image MIME type.")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise GatewayRequestError("Image data URI contains invalid base64.") from error
    return mime_type, payload


def normalize_image_data_uri(
    value: str,
    *,
    max_side: int,
    max_decoded_bytes: int,
) -> str:
    _mime_type, payload = _parse_data_uri(value)
    if len(payload) > max_decoded_bytes:
        raise GatewayRequestError("Decoded image exceeds the configured limit.")
    try:
        with Image.open(io.BytesIO(payload)) as source:
            source.load()
            image = ImageOps.exif_transpose(source)
            if image.width <= 0 or image.height <= 0:
                raise GatewayRequestError("Image dimensions are invalid.")
            if max(image.size) > max_side:
                image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

            output = io.BytesIO()
            has_alpha = image.mode in {"RGBA", "LA"} or (
                image.mode == "P" and "transparency" in image.info
            )
            if has_alpha:
                image.convert("RGBA").save(output, format="PNG", optimize=True)
                normalized_mime = "image/png"
            else:
                image.convert("RGB").save(
                    output,
                    format="JPEG",
                    quality=90,
                    optimize=True,
                    progressive=True,
                )
                normalized_mime = "image/jpeg"
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise GatewayRequestError("Image payload is not a supported safe image.") from error

    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:{normalized_mime};base64,{encoded}"


def _sanitize_content_part(
    raw_part: Mapping[str, Any],
    *,
    role: str,
    settings: GatewaySettings,
) -> tuple[dict[str, Any], bool]:
    part_type = str(raw_part.get("type") or "").strip()
    if part_type == "text":
        text = raw_part.get("text")
        if not isinstance(text, str):
            raise GatewayRequestError("Text content part must contain a string.")
        return {"type": "text", "text": text}, False
    if part_type != "image_url":
        raise GatewayRequestError("Only text and image_url content parts are supported.")
    if role != "user":
        raise GatewayRequestError("Images are accepted only in user messages.")
    image_url = raw_part.get("image_url")
    if not isinstance(image_url, Mapping):
        raise GatewayRequestError("image_url must be an object.")
    raw_url = image_url.get("url")
    if not isinstance(raw_url, str):
        raise GatewayRequestError("image_url.url must be a string.")
    return (
        {
            "type": "image_url",
            "image_url": {
                "url": normalize_image_data_uri(
                    raw_url,
                    max_side=settings.max_image_side,
                    max_decoded_bytes=settings.max_decoded_image_bytes,
                )
            },
        },
        True,
    )


def sanitize_chat_payload(
    payload: Mapping[str, Any],
    *,
    settings: GatewaySettings,
) -> dict[str, Any]:
    unknown_fields = sorted(set(payload) - _ALLOWED_REQUEST_FIELDS)
    if unknown_fields:
        raise GatewayRequestError(
            "Unsupported request fields: " + ", ".join(unknown_fields)
        )
    if payload.get("stream") not in {None, False}:
        raise GatewayRequestError("Streaming is disabled for the local VL gateway.")
    requested_model = str(payload.get("model") or settings.model).strip()
    if requested_model != settings.model:
        raise GatewayRequestError("Requested model is not available on this gateway.")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise GatewayRequestError("messages must be a non-empty list.")

    image_count = 0
    sanitized_messages: list[dict[str, Any]] = []
    for raw_message in messages:
        if not isinstance(raw_message, Mapping):
            raise GatewayRequestError("Each message must be an object.")
        role = str(raw_message.get("role") or "").strip()
        if role not in {"system", "user", "assistant"}:
            raise GatewayRequestError("Unsupported message role.")
        raw_content = raw_message.get("content")
        if isinstance(raw_content, str):
            content: str | list[dict[str, Any]] = raw_content
        elif isinstance(raw_content, list):
            normalized_parts: list[dict[str, Any]] = []
            for raw_part in raw_content:
                if not isinstance(raw_part, Mapping):
                    raise GatewayRequestError("Message content parts must be objects.")
                part, is_image = _sanitize_content_part(
                    raw_part,
                    role=role,
                    settings=settings,
                )
                if is_image:
                    image_count += 1
                    if image_count > settings.max_images:
                        raise GatewayRequestError("Too many images in one request.")
                normalized_parts.append(part)
            content = normalized_parts
        else:
            raise GatewayRequestError("Message content must be text or a parts list.")
        sanitized_messages.append({"role": role, "content": content})

    result = {key: value for key, value in payload.items() if key != "messages"}
    result["model"] = settings.model
    result["messages"] = sanitized_messages
    result["stream"] = False
    return result


async def _runtime_models(
    session: ClientSession,
    settings: GatewaySettings,
) -> tuple[str, str | None]:
    timeout = ClientTimeout(total=settings.health_timeout_seconds)
    async with session.get(
        f"{settings.runtime_base_url}/api/tags",
        timeout=timeout,
    ) as response:
        if response.status != 200:
            raise RuntimeError(f"runtime tags endpoint returned HTTP {response.status}")
        payload = await response.json(content_type=None)
    models = payload.get("models") if isinstance(payload, Mapping) else None
    if not isinstance(models, list):
        raise RuntimeError("runtime tags response has no models list")
    for item in models:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or item.get("model") or "").strip()
        if name == settings.model:
            digest = str(item.get("digest") or "").strip() or None
            return name, digest
    raise RuntimeError("configured model is not installed")


def _digest_matches(actual: str | None, expected: str | None) -> bool:
    if not expected:
        return True
    if not actual:
        return False
    return actual.casefold().startswith(expected.casefold())


async def health(request: web.Request) -> web.Response:
    settings: GatewaySettings = request.app["settings"]
    session: ClientSession = request.app["session"]
    try:
        model, digest = await _runtime_models(session, settings)
        if not _digest_matches(digest, settings.expected_digest):
            raise RuntimeError("installed model digest does not match expected digest")
    except (ClientError, asyncio.TimeoutError, RuntimeError, ValueError) as error:
        return web.json_response(
            {"status": "unhealthy", "reason": str(error)},
            status=503,
        )
    return web.json_response(
        {
            "status": "healthy",
            "model": model,
            "digest": digest,
            "max_concurrency": settings.max_concurrency,
            "max_image_side": settings.max_image_side,
        }
    )


async def models(request: web.Request) -> web.Response:
    settings: GatewaySettings = request.app["settings"]
    session: ClientSession = request.app["session"]
    try:
        model, digest = await _runtime_models(session, settings)
        if not _digest_matches(digest, settings.expected_digest):
            raise RuntimeError("installed model digest does not match expected digest")
    except (ClientError, asyncio.TimeoutError, RuntimeError, ValueError) as error:
        return web.json_response({"error": {"message": str(error)}}, status=503)
    return web.json_response(
        {
            "object": "list",
            "data": [
                {
                    "id": model,
                    "object": "model",
                    "owned_by": "velvet-local",
                    "digest": digest,
                }
            ],
        }
    )


async def chat_completions(request: web.Request) -> web.Response:
    settings: GatewaySettings = request.app["settings"]
    session: ClientSession = request.app["session"]
    semaphore: asyncio.Semaphore = request.app["semaphore"]
    request_id = request.headers.get("X-Request-ID", "")[:128]
    try:
        payload = await request.json(loads=json.loads)
        if not isinstance(payload, Mapping):
            raise GatewayRequestError("Request body must be a JSON object.")
        sanitized = sanitize_chat_payload(payload, settings=settings)
    except (ValueError, TypeError, UnicodeDecodeError, web.HTTPRequestEntityTooLarge) as error:
        return web.json_response({"error": {"message": str(error)}}, status=400)

    started = time.monotonic()
    try:
        async with semaphore:
            timeout = ClientTimeout(total=settings.request_timeout_seconds)
            async with session.post(
                f"{settings.runtime_base_url}/v1/chat/completions",
                json=sanitized,
                timeout=timeout,
            ) as response:
                body = await response.read()
                status = response.status
                content_type = response.headers.get("Content-Type", "application/json")
    except asyncio.TimeoutError:
        return web.json_response(
            {"error": {"message": "Local VL runtime timed out."}},
            status=504,
        )
    except ClientError:
        logger.exception("Local VL runtime request failed request_id=%s", request_id)
        return web.json_response(
            {"error": {"message": "Local VL runtime is unavailable."}},
            status=502,
        )
    finally:
        logger.info(
            "VL request completed request_id=%s model=%s duration_ms=%d",
            request_id,
            settings.model,
            int((time.monotonic() - started) * 1000),
        )

    return web.Response(
        body=body,
        status=status,
        content_type=content_type.split(";", 1)[0],
    )


async def _session_context(app: web.Application):
    timeout = ClientTimeout(total=None)
    session = ClientSession(timeout=timeout, raise_for_status=False)
    app["session"] = session
    try:
        yield
    finally:
        await session.close()


def create_app(settings: GatewaySettings | None = None) -> web.Application:
    resolved = settings or GatewaySettings.from_env()
    _validate_runtime_base_url(resolved.runtime_base_url)
    app = web.Application(client_max_size=resolved.client_max_size)
    app["settings"] = resolved
    app["semaphore"] = asyncio.Semaphore(resolved.max_concurrency)
    app.cleanup_ctx.append(_session_context)
    app.router.add_get("/health", health)
    app.router.add_get("/v1/models", models)
    app.router.add_post("/v1/chat/completions", chat_completions)
    return app


def main() -> None:
    logging.basicConfig(
        level=os.getenv("VISION_GATEWAY_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    settings = GatewaySettings.from_env()
    web.run_app(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()


__all__ = (
    "GatewayRequestError",
    "GatewaySettings",
    "create_app",
    "normalize_image_data_uri",
    "sanitize_chat_payload",
)
