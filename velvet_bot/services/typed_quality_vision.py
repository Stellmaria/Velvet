from __future__ import annotations

import asyncio
import base64
import io
import json
from collections.abc import Mapping

from PIL import Image, ImageOps, UnidentifiedImageError

from velvet_bot.ai_quality import (
    QualityVisionClient,
    build_quality_vision_contract,
    normalize_quality_report,
)
from velvet_bot.ai_vision import VisionAnalysisError
from velvet_bot.domains.vision_routing.failures import (
    VisionRefusalError,
    VisionSchemaError,
    schema_failure,
)
from velvet_bot.domains.vision_routing.http import post_vision_json

_MAX_IMAGE_SIDE = 1280


def _prepare_quality_image(source: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(source)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            image.load()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise VisionAnalysisError("Файл не удалось прочитать как изображение.") from error
    try:
        image.thumbnail((_MAX_IMAGE_SIDE, _MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=86, optimize=True)
        return output.getvalue()
    finally:
        image.close()


def _openai_content(payload: Mapping[str, object]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise VisionSchemaError("Quality VL endpoint не вернул choices.")
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    if not isinstance(message, dict):
        raise VisionSchemaError("Quality VL endpoint не вернул message.")
    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal.strip():
        raise VisionRefusalError(f"provider refusal: {refusal.strip()}")
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        fragments = [
            str(item.get("text") or "").strip()
            for item in content
            if isinstance(item, dict) and str(item.get("text") or "").strip()
        ]
        if fragments:
            return "\n".join(fragments)
    raise VisionSchemaError("Quality VL endpoint не вернул текст.")


class TypedQualityVisionClient(QualityVisionClient):
    """Quality client with cancellable HTTP and no automatic full-image resend."""

    async def analyze(self, source: bytes) -> dict[str, object]:
        prepared = await asyncio.to_thread(_prepare_quality_image, source)
        image_base64 = base64.b64encode(prepared).decode("ascii")
        contract = build_quality_vision_contract()
        prompt = self._schema_prompt()

        if self.provider == "ollama":
            body: dict[str, object] = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [image_base64],
                    }
                ],
                "format": contract.schema,
                "stream": False,
                "think": False,
                "options": {
                    "temperature": 0,
                    "num_predict": contract.max_output_tokens,
                },
            }
            payload = await post_vision_json(
                url=f"{self.base_url}/api/chat",
                body=body,
                headers=self._headers(),
                timeout_seconds=self.timeout_seconds,
            )
            try:
                return self._parse_ollama_payload(payload)
            except VisionAnalysisError as error:
                raise schema_failure(error) from error

        root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            },
                        },
                    ],
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "velvet_personal_quality",
                    "strict": True,
                    "schema": contract.schema,
                },
            },
            "temperature": 0,
            "max_tokens": contract.max_output_tokens,
        }
        payload = await post_vision_json(
            url=f"{root}/v1/chat/completions",
            body=body,
            headers=self._headers(),
            timeout_seconds=self.timeout_seconds,
        )
        content = _openai_content(payload)
        try:
            parsed = json.loads(content)
            return normalize_quality_report(parsed)
        except (json.JSONDecodeError, VisionAnalysisError) as error:
            raise schema_failure(error) from error


__all__ = ("TypedQualityVisionClient",)
