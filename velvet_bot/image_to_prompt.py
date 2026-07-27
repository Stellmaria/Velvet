from __future__ import annotations

import asyncio
import base64
import json
import urllib.request
from typing import Any

from velvet_bot.ai_vision import (
    VisionAnalysisError,
    VisionClient,
    _prepare_image,
)

_IMAGE_TO_PROMPT_INSTRUCTION = """
Проанализируй изображение как техническое задание для генеративной модели.
Опиши только то, что действительно видно, не выдумывай скрытые детали и не
пытайся определять личность реального человека. Все изображённые люди должны
трактоваться как взрослые; если возраст выглядит неоднозначно, не описывай
сексуализированные детали и прямо отметь неопределённость.

Сформируй практичный промт на русском языке. Сохрани точную композицию,
количество персонажей, внешность, телосложение, одежду, позы, положение рук и
ног, направление взгляда, выражения лиц, взаимодействие, окружение, предметы,
ракурс, кадрирование, предполагаемый объектив, глубину резкости, освещение,
тени, цветовую температуру, палитру, материалы, фактуры и художественный стиль.
Для взрослой художественной наготы используй точные нейтральные формулировки,
не смягчая видимые детали и не добавляя действий, которых нет в кадре.

Ответ дай без вводных фраз в таком формате:

ОСНОВНОЙ ПРОМТ
<единый подробный промт>

NEGATIVE PROMPT
<ошибки анатомии, лишние конечности и пальцы, артефакты, текст, watermark,
искажения перспективы и другие нежелательные признаки, уместные для кадра>

КАМЕРА И КОМПОЗИЦИЯ
<краткие технические параметры>

СВЕТ И ЦВЕТ
<краткие технические параметры>
""".strip()


class ImageToPromptClient(VisionClient):
    """Generate a reusable image-generation prompt from one source image."""

    async def generate(self, source: bytes) -> str:
        prepared = await asyncio.to_thread(_prepare_image, source)
        image_base64 = base64.b64encode(prepared).decode("ascii")

        if self.provider == "ollama":
            url = f"{self.base_url}/api/chat"
            body: dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": _IMAGE_TO_PROMPT_INSTRUCTION,
                        "images": [image_base64],
                    }
                ],
                "stream": False,
                "think": False,
                "keep_alive": "15m",
                "options": {
                    "temperature": 0.2,
                    "num_predict": 2400,
                },
            }
        else:
            root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
            url = f"{root}/v1/chat/completions"
            body = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": _IMAGE_TO_PROMPT_INSTRUCTION},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                },
                            },
                        ],
                    }
                ],
                "temperature": 0.2,
                "max_tokens": 2400,
            }

        request = urllib.request.Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        payload = await asyncio.to_thread(
            self._read_json,
            request,
            timeout=self.timeout_seconds,
        )

        if self.provider == "ollama":
            message = payload.get("message")
            content = message.get("content") if isinstance(message, dict) else ""
            if not content:
                content = payload.get("response")
        else:
            choices = payload.get("choices")
            first = choices[0] if isinstance(choices, list) and choices else {}
            message = first.get("message") if isinstance(first, dict) else {}
            content = message.get("content") if isinstance(message, dict) else ""

        result = str(content or "").strip()
        if result.startswith("```") and result.endswith("```"):
            lines = result.splitlines()
            result = "\n".join(lines[1:-1]).strip()
        if len(result) < 40:
            raise VisionAnalysisError("Qwen не вернул пригодный промт по изображению.")
        return result[:16000]


__all__ = ("ImageToPromptClient",)
