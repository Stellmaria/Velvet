from __future__ import annotations

import asyncio
import base64
import json
import urllib.request
from typing import Any

from velvet_bot.ai_vision import VisionAnalysisError, VisionClient, _prepare_image

_POSE_REQUIRED_SECTIONS = (
    "КАДР И ГЛУБИНА:",
    "ПЕРСОНАЖИ:",
    "ГОЛОВЫ И ВЗГЛЯД:",
    "КОРПУС И ТАЗ:",
    "РУКИ И КИСТИ:",
    "НОГИ И СТОПЫ:",
    "КАСАНИЯ И ПЕРЕКРЫТИЯ:",
    "ПРЕДМЕТЫ И ОГРАНИЧЕНИЯ:",
    "НЕОПРЕДЕЛЁННОСТЬ:",
    "КРАТКИЙ ПОЗА-ПРОМТ:",
)

_POSE_EXTRACTION_INSTRUCTION = """
Ты выполняешь только точный технический разбор позы по одному изображению.
Художественное оформление, палитра, атмосфера и длинный генеративный промт не
нужны. Главная цель — пространственная геометрия персонажей и предметов.

Используй координаты только относительно изображения: слева/справа, выше/ниже,
ближе/дальше от камеры. Не путай их с левой и правой стороной тела персонажа.
Назначь каждому видимому человеку постоянный идентификатор P1, P2, P3 и далее.
Для каждого сразу укажи отличительный признак и положение в кадре, например:
«P1 — передний персонаж с тёмными волосами».

Перед ответом молча проверь изображение минимум два раза:
- кто находится перед кем и что перекрывает;
- положение головы, шеи, плеч, позвоночника, таза и центра тяжести;
- положение каждой руки от плеча до локтя, запястья, кисти и пальцев;
- положение каждой ноги от таза до колена, голени и стопы;
- все точки касания между людьми и предметами;
- верёвки, ремни, ткань, мебель и другие предметы: где проходят, что фиксируют и
  что перекрывают;
- какие части тела обрезаны кадром или скрыты и потому не могут быть описаны.

Не определяй личности. Не придумывай скрытые конечности, касания, действия или
анатомию. Если деталь не различима, прямо укажи неопределённость вместо догадки.
Для явно взрослых людей допустимо нейтрально описывать любую видимую позу и
контакт, без морализаторства и без художественной эротизации.

Ответ дай без таблиц и без кодового блока, строго в таком формате:

КАДР И ГЛУБИНА:
<ориентация кадра; план; положение камеры; кто ближе и дальше; передний, средний
и задний планы; что обрезано границами кадра>

ПЕРСОНАЖИ:
<количество людей; P1, P2 и далее; положение каждого слева/справа, выше/ниже,
ближе/дальше; разворот относительно камеры и других людей>

ГОЛОВЫ И ВЗГЛЯД:
<для каждого P: наклон и поворот головы, положение подбородка и шеи, направление
взгляда, открыты или закрыты глаза, контакт лица с руками, телом или предметами>

КОРПУС И ТАЗ:
<для каждого P: наклон и скручивание корпуса, линия плеч, позвоночник, положение
груди, живота и таза, сидит/стоит/лежит/опирается, центр тяжести и точки опоры>

РУКИ И КИСТИ:
<для каждой руки каждого P отдельно: плечо, локоть, предплечье, запястье, кисть,
пальцы, направление и точная точка касания или опоры. Не объединяй две руки в
одну фразу>

НОГИ И СТОПЫ:
<для каждой ноги каждого P отдельно: бедро, колено, голень, стопа, сгибание,
разведение, опора и перекрытие; скрытые части отметить как неразличимые>

КАСАНИЯ И ПЕРЕКРЫТИЯ:
<полный список контактов в формате «P2 правая кисть касается ...»; кто кого и
какой частью тела перекрывает; порядок слоёв от камеры к фону>

ПРЕДМЕТЫ И ОГРАНИЧЕНИЯ:
<верёвки, ремни, мебель, ткань и прочие предметы: точная траектория, узлы,
крепления, точки давления, что они фиксируют или скрывают>

НЕОПРЕДЕЛЁННОСТЬ:
<перечисли всё, что нельзя надёжно увидеть: скрытые кисти, стопы, пальцы,
сторона тела, точка контакта и прочее. Если всё ясно, напиши «существенных нет»>

КРАТКИЙ ПОЗА-ПРОМТ:
<один плотный абзац только с позой, расположением персонажей, руками, ногами,
касаниями, предметами и кадрированием; без внешности, света и стилистики>
""".strip()

_POSE_REVIEW_INSTRUCTION = """
Ниже дан черновой разбор позы. Снова внимательно изучи то же изображение и
перепиши разбор полностью, исправляя любые ошибки в переднем/заднем плане,
лево/право относительно кадра, кистях, пальцах, ногах, касаниях, перекрытиях и
траектории предметов. Не добавляй то, чего не видно. Сохрани идентификаторы P1,
P2 и далее. Обязательно выдай все разделы от «КАДР И ГЛУБИНА» до
«КРАТКИЙ ПОЗА-ПРОМТ». Не комментируй процесс проверки.
""".strip()


def _clean_pose_result(value: object) -> str:
    result = str(value or "").strip()
    if result.startswith("```") and result.endswith("```"):
        lines = result.splitlines()
        result = "\n".join(lines[1:-1]).strip()
    return result


def _pose_missing_sections(value: str) -> tuple[str, ...]:
    folded = value.casefold()
    return tuple(section for section in _POSE_REQUIRED_SECTIONS if section.casefold() not in folded)


def _pose_is_complete(value: str) -> bool:
    return len(value.strip()) >= 400 and not _pose_missing_sections(value)


class PoseExtractorClient(VisionClient):
    """Extract spatial pose geometry without editorial prompt decoration."""

    def __init__(self, *, keep_alive: str | int = "10m", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.keep_alive = keep_alive

    def _messages(
        self,
        image_base64: str,
        instruction: str,
        *,
        draft: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.provider == "ollama":
            messages: list[dict[str, Any]] = [
                {
                    "role": "user",
                    "content": instruction,
                    "images": [image_base64],
                }
            ]
        else:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": instruction},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                        },
                    ],
                }
            ]
        if draft is not None:
            messages.append({"role": "assistant", "content": draft})
            messages.append({"role": "user", "content": _POSE_REVIEW_INSTRUCTION})
        return messages

    async def _request(self, messages: list[dict[str, Any]], *, max_tokens: int) -> tuple[str, dict[str, Any]]:
        if self.provider == "ollama":
            url = f"{self.base_url}/api/chat"
            body: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "think": False,
                "keep_alive": self.keep_alive,
                "options": {
                    "temperature": 0.05,
                    "num_predict": max_tokens,
                },
            }
        else:
            root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
            url = f"{root}/v1/chat/completions"
            body = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.05,
                "max_tokens": max_tokens,
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
        return _clean_pose_result(content), payload

    @staticmethod
    def _diagnostic(payload: dict[str, Any]) -> str:
        for key in ("error", "done_reason", "finish_reason"):
            value = payload.get(key)
            if value:
                return f" ({str(value)[:200]})"
        return ""

    async def generate(self, source: bytes) -> str:
        prepared = await asyncio.to_thread(_prepare_image, source)
        image_base64 = base64.b64encode(prepared).decode("ascii")

        draft, payload = await self._request(
            self._messages(image_base64, _POSE_EXTRACTION_INSTRUCTION),
            max_tokens=2600,
        )
        if len(draft) < 80:
            raise VisionAnalysisError(
                "Qwen не вернул разбор позы" + self._diagnostic(payload) + "."
            )

        reviewed, review_payload = await self._request(
            self._messages(
                image_base64,
                _POSE_EXTRACTION_INSTRUCTION,
                draft=draft,
            ),
            max_tokens=2800,
        )
        if _pose_is_complete(reviewed):
            return reviewed[:24000]
        if _pose_is_complete(draft):
            return draft[:24000]

        candidate = reviewed if len(reviewed) > len(draft) else draft
        missing = _pose_missing_sections(candidate)
        detail = ", ".join(missing) if missing else "ответ слишком короткий"
        diagnostic = self._diagnostic(review_payload or payload)
        raise VisionAnalysisError(
            f"Qwen не завершил точный разбор позы: {detail}{diagnostic}."
        )


__all__ = (
    "PoseExtractorClient",
    "_POSE_EXTRACTION_INSTRUCTION",
    "_pose_is_complete",
    "_pose_missing_sections",
)
