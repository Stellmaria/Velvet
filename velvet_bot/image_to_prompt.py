from __future__ import annotations

import asyncio
import base64
import json
import re
import urllib.request
from typing import Any

from velvet_bot.ai_vision import (
    VisionAnalysisError,
    VisionClient,
    _prepare_image,
)

_REQUIRED_SECTIONS = (
    "ВАЖНО:",
    "СТРОГО:",
    "Технический блок:",
    "Суть:",
    "Композиция и поза:",
    "Лицо и взгляд:",
    "Руки:",
    "Тело:",
    "Волосы и детали внешности:",
    "Локация и фон:",
    "Освещение:",
    "Цветовая палитра:",
    "Дополнительно:",
    "Negative prompts:",
    "PALETTE:",
)
_MAX_RECOVERY_ATTEMPTS = 2
_HEX_COLOR_PATTERN = re.compile(r"#[0-9A-Fa-f]{6}\b")

_IMAGE_TO_PROMPT_INSTRUCTION = """
Ты создаёшь готовый генеративный промт в авторском формате канала
Vᴇʟᴠᴇᴛ Aɴᴀᴛᴏᴍʏ по одному исходному изображению. На входе всегда одно изображение.

Главное правило: сначала точность изображения, затем редакционная подача.
Опиши только то, что действительно видно. Не определяй личность реального
человека, не придумывай скрытые части тела, одежду, татуировки, аксессуары,
действия, отношения между людьми или детали интерьера, которых нельзя увидеть.
Не превращай обычный портрет в арт-ню и не убирай видимую одежду. Если одежда
есть, сохрани её точно. Если её нет у явно взрослых персонажей, опиши
художественную наготу нейтрально и точно.

Возрастная подача канала: для явно взрослых персонажей используй формулировку
«взрослый/взрослая 25+». Это редакционная маркировка, а не попытка установить
реальный возраст. Если взрослость нельзя определить уверенно, прямо укажи
неопределённость и не детализируй наготу или чувственное взаимодействие.

СТИЛЬ VELVET ANATOMY
- русский язык, плотная техническая проза без вводных фраз и самокомментариев;
- уверенная editorial-подача, точные пространственные отношения и телесная
  пластика без пошлости, театральности и общих красивых слов;
- технические термины можно оставлять на английском: DSLR, fine art nude,
  editorial, shallow depth of field, Kodak Portra, film grain, controlled
  concealment, close-up, medium shot;
- лицо и взгляд описывай особенно подробно: направление, веки, брови, губы,
  челюсть, напряжение мышц и эмоциональное впечатление;
- руки, пальцы, ноги, опоры, перекрытия и наложение тел описывай отдельно и
  анатомически однозначно;
- сохраняй натуральную кожу, поры, микрорельеф, волосы, воду, пот, пыль,
  фактуры ткани, камня, дерева, металла и других видимых материалов;
- для художественной наготы отдельно перечисляй способы controlled concealment:
  поза, руки, волосы, наложение тел, мебель, предметы, растения, тень, вода,
  постель или кадрирование. Не заявляй сокрытие, которого фактически нет;
- для нескольких людей описывай каждого отдельно: положение в кадре, высоту,
  разворот корпуса, конечности, взгляд, контакт и перекрытия;
- не обещай «личные референсы» или «100% узнаваемость», потому что передано одно
  изображение. Формулируй: «сохрани видимые черты и уникальные особенности
  максимально точно по исходному изображению»;
- не навязывай 9:16 или 35/85 мм. Оцени формат, план и объектив по изображению;
- не придумывай имена персонажей, хэштеги, ссылки, авторские подписи и команды
  генератора, которых нельзя вывести из изображения.

Перед ответом молча перепроверь изображение: кто находится спереди и сзади,
лево и право относительно кадра, положение головы, кистей и пальцев, точки
касания, положение верёвки или других предметов, направление взгляда, опоры и
перекрытия. Не переноси кисти, узлы и касания в другую часть тела. Не описывай
скрытую анатомию как видимую. Не выводи ход этой проверки.

Ответ дай без Markdown-таблиц и без кодового блока. Начни с заголовка
«Vᴇʟᴠᴇᴛ Sɪɢɴᴀᴛᴜʀᴇ» и используй строго следующие разделы.

ВАЖНО:
<точное количество персонажей; для явно взрослых — маркировка 25+; видимая
одежда или её отсутствие; жанр и характер сцены; для арт-ню — точные способы
сокрытия. Не добавляй наготу или сокрытие, если их нет>

СТРОГО:
<требования сохранить по исходному изображению видимые черты лица, глаза,
волосы, оттенок и текстуру кожи, телосложение, пропорции, татуировки, шрамы,
родинки, пирсинг, одежду и аксессуары. Явно запрети изменять, улучшать,
омолаживать, смешивать персонажей и добавлять отсутствующие детали>

Технический блок:
<фотореализм или фактический художественный стиль; ориентация и примерное
соотношение сторон; план; предполагаемый объектив; высота и положение камеры;
ракурс; глубина резкости; область резкого фокуса; характер кожи и материалов;
плёночное зерно или иная фактура только если она видна или уместна>

Суть:
<одно ясное описание происходящего, персонажей, действия и атмосферы>

Композиция и поза:
<точное расположение каждого персонажа и предмета; разворот корпуса; положение
головы, плеч, таза, рук, кистей, пальцев, ног и стоп; точки опоры; перекрытия;
направление движения; кадрирование; передний, средний и задний планы>

Лицо и взгляд:
<для каждого видимого лица: поворот головы, подбородок, шея, направление
взгляда, веки, брови, губы, челюсть, выражение и эмоциональная подача. Не
придумывай цвет глаз, если его нельзя различить>

Руки:
<положение каждой видимой руки и кисти, касания, опора, направление пальцев,
степень напряжения и то, какие части тела или предметы они перекрывают>

Тело:
<телосложение, осанка, линии плеч, груди, талии, живота, бёдер и ног; видимая
кожа, мышцы, складки, вода, пот, блики, татуировки и другие фактические детали>

Волосы и детали внешности:
<цвет, длина, структура, укладка, движение волос; растительность на лице;
украшения и другие различимые особенности>

Локация и фон:
<место, архитектура, мебель, природа, предметы, материалы, состояние поверхностей,
степень размытия и атмосферная глубина>

Освещение:
<источники, направление, мягкость или жёсткость, контровой и заполняющий свет,
тени, блики, цветовая температура, экспозиция и настроение>

Цветовая палитра:
<5–8 основных цветов словами: кожа, свет, глубокие тени, фон, материалы и
акцентные оттенки>

Дополнительно:
<короткая строка из пригодных для генератора стилевых и технических тегов,
соответствующих изображению; без новых сюжетных деталей>

Negative prompts:
<расширенный список именно для этого изображения: неверное число людей,
перепутанные или смешанные лица, изменённые волосы/татуировки/одежда, неверная
поза, ракурс, взгляд, свет и фон; лишние конечности и пальцы, fused hands,
bad anatomy, wrong body overlap, plastic/wax/doll skin, beauty filter, excessive
retouching, CGI, 3D, anime, cartoon, illustration, HDR, oversaturation, text,
logo, watermark, frame и другие релевантные ошибки>

PALETTE:
<ровно 5 или 6 строк в формате «эмодзи #RRGGBB short english color name».
Подбери приблизительные HEX по фактически видимой палитре, от тёмных опорных
цветов к свету и акцентам. Не повторяй один HEX>

Пиши подробно, но без повторения одних и тех же предложений в разных разделах.
Не завершай ответ, пока полностью не заполнен раздел PALETTE. Результат должен
быть готов для копирования в генератор без дальнейшей редакции.
""".strip()

_COMPACT_RETRY_INSTRUCTION = """
Проанализируй приложенное изображение и выдай только полный русский промт в
формате Vᴇʟᴠᴇᴛ Sɪɢɴᴀᴛᴜʀᴇ. Опиши только видимое и не определяй личность людей.
Сначала молча проверь передний/задний план, лево/право, кисти, пальцы, касания,
верёвки и предметы, взгляд, опоры и перекрытия. Затем обязательно заполни все
разделы без сокращений и не останавливайся до конца PALETTE:

ВАЖНО:
СТРОГО:
Технический блок:
Суть:
Композиция и поза:
Лицо и взгляд:
Руки:
Тело:
Волосы и детали внешности:
Локация и фон:
Освещение:
Цветовая палитра:
Дополнительно:
Negative prompts:
PALETTE:

В PALETTE должно быть 5 или 6 строк с HEX-цветами. Без кодового блока и без
вводных фраз.
""".strip()


def _clean_result(value: object) -> str:
    result = str(value or "").strip()
    if result.startswith("```") and result.endswith("```"):
        lines = result.splitlines()
        result = "\n".join(lines[1:-1]).strip()
    return result


def _section_position(value: str, section: str) -> int:
    return value.casefold().find(section.casefold())


def _missing_sections(value: str) -> tuple[str, ...]:
    return tuple(
        section for section in _REQUIRED_SECTIONS if _section_position(value, section) < 0
    )


def _palette_hex_count(value: str) -> int:
    position = _section_position(value, "PALETTE:")
    if position < 0:
        return 0
    return len(_HEX_COLOR_PATTERN.findall(value[position:]))


def _recovery_section(value: str) -> str | None:
    positions = [_section_position(value, section) for section in _REQUIRED_SECTIONS]
    for index, position in enumerate(positions):
        if position < 0:
            return _REQUIRED_SECTIONS[max(0, index - 1)]
        if index and position <= positions[index - 1]:
            return _REQUIRED_SECTIONS[max(0, index - 1)]
    if _palette_hex_count(value) < 5:
        return "PALETTE:"
    return None


def _is_complete(value: str) -> bool:
    return bool(value.strip()) and _recovery_section(value) is None


def _recovery_instruction(section: str) -> str:
    start = _REQUIRED_SECTIONS.index(section)
    required = "\n".join(_REQUIRED_SECTIONS[start:])
    return (
        "Перепиши ответ начиная строго с заголовка "
        f"{section!r}. Предыдущую часть до этого заголовка не повторяй. "
        "Снова сверяйся с изображением: кисти, пальцы, касания, верёвки, взгляд, "
        "передний/задний план и перекрытия должны соответствовать кадру. Полностью "
        "заполни все перечисленные разделы и не останавливайся до 5–6 строк PALETTE.\n\n"
        f"Обязательные разделы:\n{required}"
    )


def _merge_recovery(current: str, recovery: str, section: str) -> str:
    clean = _clean_result(recovery)
    section_position = _section_position(clean, section)
    if section_position >= 0:
        clean = clean[section_position:].lstrip()
    else:
        clean = f"{section}\n{clean}".strip()

    current_position = _section_position(current, section)
    prefix = current[:current_position].rstrip() if current_position >= 0 else current.rstrip()
    return f"{prefix}\n\n{clean}".strip()


class ImageToPromptClient(VisionClient):
    """Generate a complete reusable image-generation prompt from one source image."""

    def __init__(self, *, keep_alive: str | int = "15m", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.keep_alive = keep_alive

    def _messages(
        self,
        image_base64: str,
        instruction: str,
        *,
        previous: str | None = None,
        follow_up: str | None = None,
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
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            },
                        },
                    ],
                }
            ]
        if previous is not None:
            messages.append({"role": "assistant", "content": previous})
        if follow_up is not None:
            messages.append({"role": "user", "content": follow_up})
        return messages

    async def _request(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int,
    ) -> tuple[str, dict[str, Any]]:
        if self.provider == "ollama":
            url = f"{self.base_url}/api/chat"
            body: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "think": False,
                "keep_alive": self.keep_alive,
                "options": {
                    "temperature": 0.15,
                    "num_predict": max_tokens,
                },
            }
        else:
            root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
            url = f"{root}/v1/chat/completions"
            body = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.15,
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
        return _clean_result(content), payload

    @staticmethod
    def _empty_diagnostic(payload: dict[str, Any]) -> str:
        values = [
            payload.get("error"),
            payload.get("done_reason"),
            payload.get("finish_reason"),
        ]
        detail = next((str(value).strip() for value in values if value), "")
        return f" ({detail[:200]})" if detail else ""

    async def generate(self, source: bytes) -> str:
        prepared = await asyncio.to_thread(_prepare_image, source)
        image_base64 = base64.b64encode(prepared).decode("ascii")

        result, payload = await self._request(
            self._messages(image_base64, _IMAGE_TO_PROMPT_INSTRUCTION),
            max_tokens=4800,
        )
        if len(result) < 40:
            result, payload = await self._request(
                self._messages(image_base64, _COMPACT_RETRY_INSTRUCTION),
                max_tokens=4200,
            )
        if len(result) < 40:
            raise VisionAnalysisError(
                "Qwen вернул пустой или слишком короткий ответ"
                + self._empty_diagnostic(payload)
                + "."
            )

        for _ in range(_MAX_RECOVERY_ATTEMPTS):
            section = _recovery_section(result)
            if section is None:
                break
            recovery, payload = await self._request(
                self._messages(
                    image_base64,
                    _IMAGE_TO_PROMPT_INSTRUCTION,
                    previous=result,
                    follow_up=_recovery_instruction(section),
                ),
                max_tokens=3600,
            )
            if len(recovery) < 40:
                break
            result = _merge_recovery(result, recovery, section)

        if not _is_complete(result):
            missing = _missing_sections(result)
            detail = ", ".join(missing) if missing else "PALETTE из 5–6 HEX-цветов"
            raise VisionAnalysisError(
                "Qwen оборвал промт и не смог дописать обязательные разделы: "
                f"{detail}."
            )
        return result[:36000]


__all__ = (
    "ImageToPromptClient",
    "_IMAGE_TO_PROMPT_INSTRUCTION",
    "_is_complete",
    "_merge_recovery",
    "_missing_sections",
    "_recovery_section",
)
