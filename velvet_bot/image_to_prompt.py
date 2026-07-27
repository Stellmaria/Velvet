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
Опиши только то, что действительно видно в кадре. Не выдумывай скрытые детали,
не определяй личность реального человека и не добавляй действий, которых нет на
изображении.

Все изображённые люди должны быть явно взрослыми. Если по изображению нельзя
уверенно заключить, что человек взрослый, прямо отметь неопределённость и не
детализируй наготу или чувственное взаимодействие. Для явно взрослых людей
художественную наготу описывай точно, нейтрально и без смягчения видимых деталей.
Отдельно указывай способы сокрытия: руками, волосами, позой, перекрытием тел,
мебелью, предметами, растениями, тенями или кадрированием.

Сформируй практичный промт на русском языке в эстетике Velvet Anatomy. Сохрани
количество персонажей, внешность, телосложение, одежду или её отсутствие, позы,
положение головы, рук и ног, направление взгляда, выражения лиц,
взаимодействие, окружение, предметы, ракурс, кадрирование, предполагаемый
объектив, глубину резкости, освещение, тени, цветовую температуру, палитру,
материалы, фактуры и художественный стиль.

Не утверждай, что внешность сохранена по личным референсам, если референсы не
переданы. Вместо этого формулируй требование сохранить видимые особенности
персонажей по исходному изображению.

Ответ дай без вводных фраз и строго в таком формате:

ВАЖНО
<количество явно взрослых персонажей, одежда или её отсутствие, характер сцены,
художественная нагота и способы сокрытия видимой анатомии>

СТРОГО
<какие видимые черты лиц, кожи, волос, телосложения, пропорций, татуировок,
шрамов, родинок, пирсинга и других особенностей необходимо сохранить>

ТЕХБЛОК
<фотореализм или иной стиль, формат кадра, объектив, положение камеры, план,
глубина резкости, фокус, фактура кожи и запреты на неуместную стилизацию>

СУТЬ И ПОЗА
<подробное описание сцены, положения тел, рук и ног, взаимодействия, жестов,
перекрытий и композиционных линий>

ЛИЦА
<направление взгляда, выражения, эмоции и положение головы каждого персонажа>

ТЕЛА И ВОЛОСЫ
<телосложение, осанка, видимые особенности тела, цвет, длина, структура и
укладка волос>

ЛОКАЦИЯ
<место действия, окружение, мебель, архитектура, предметы, передний и задний план>

СВЕТ
<источники, направление, жёсткость, тени, цветовая температура и атмосфера>

NEGATIVE
<анатомические ошибки, лишние конечности и пальцы, неверное наложение тел,
ошибочная поза или камера, изменённые лица и волосы, лишние предметы, plastic
skin, CGI, 3D, anime, cartoon, illustration, HDR, text, logo, watermark и другие
нежелательные признаки, уместные для конкретного кадра>
""".strip()


class ImageToPromptClient(VisionClient):
    """Generate a reusable image-generation prompt from one source image."""

    def __init__(self, *, keep_alive: str | int = "15m", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.keep_alive = keep_alive

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
                "keep_alive": self.keep_alive,
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
