from __future__ import annotations

import asyncio
import base64

from velvet_bot.ai_vision import VisionAnalysisError, _prepare_image
from velvet_bot.infrastructure.image_to_prompt import ImageToPromptClient

POSE_EXTRACTOR_MARKER = "VELVET_AI:POSE_EXTRACTOR"

_POSE_SECTIONS = (
    "Vᴇʟᴠᴇᴛ Pᴏsᴇ",
    "Количество персонажей:",
    "Общая схема позы:",
    "Голова и шея:",
    "Корпус и таз:",
    "Руки и кисти:",
    "Ноги и стопы:",
    "Опоры и баланс:",
    "Контакты и перекрытия:",
    "Ракурс и кадрирование:",
    "Готовый pose prompt:",
    "Negative prompts:",
)

_POSE_EXTRACTION_INSTRUCTION = """
Ты извлекаешь из одного изображения только геометрию человеческой позы для
повторного использования в генераторе изображений. Не создавай полноценный
художественный промт и не пересказывай сюжет кадра. Нужна точная техническая
карта положения тел.

ОПИРАЙСЯ ТОЛЬКО НА ВИДИМОЕ
- не определяй личность, имя, этничность, состояние здоровья или отношения людей;
- не описывай красоту, привлекательность, характер, эмоции, одежду, причёску,
  татуировки, интерьер, свет, цветовую палитру и стиль съёмки, если это не нужно
  для понимания опоры или перекрытия;
- не додумывай скрытые суставы и части тела; прямо отмечай, что они не видны;
- не описывай интимную анатомию и не превращай контакт тел в сексуальное действие;
- если взрослость персонажа нельзя определить уверенно, сохраняй полностью
  нейтральную анатомическую лексику и описывай только положение тела;
- лево и право указывай относительно самого персонажа, а при риске путаницы
  добавляй положение относительно кадра;
- для нескольких людей используй обозначения «персонаж A», «персонаж B» и далее;
- отдельно проверяй голову, плечи, позвоночник, грудную клетку, таз, локти,
  запястья, кисти, пальцы, колени, лодыжки, стопы, точки опоры и центр тяжести;
- точно фиксируй, какая конечность находится ближе к камере, что перекрывает
  другое тело или предмет и где происходит фактическое касание;
- различай стояние, сидение, лежание, упор, вис, шаг, присед, прогиб, скручивание,
  перенос веса и промежуточное движение;
- не называй объектив в миллиметрах. Описывай только высоту камеры, направление,
  перспективное сокращение и границы кадра, которые влияют на чтение позы.

Перед ответом молча перепроверь количество людей, лево и право, передний и задний
план, порядок перекрытий, видимость кистей и стоп, точки касания и опоры. Не
выводи ход проверки.

Ответ дай без Markdown-таблиц и без кодового блока. Начни с заголовка
«Vᴇʟᴠᴇᴛ Pᴏsᴇ» и используй строго следующие разделы в указанном порядке.

Количество персонажей:
<точное число видимых людей; кто расположен ближе и дальше от камеры>

Общая схема позы:
<для каждого персонажа: стоя, сидя, лежит или движется; направление тела;
основная линия действия; степень симметрии; общий перенос веса>

Голова и шея:
<наклон, поворот и запрокидывание головы; положение подбородка; изгиб и напряжение
шеи; направление лица без описания внешности>

Корпус и таз:
<разворот плеч и грудной клетки; наклон и скручивание позвоночника; положение
живота, поясницы и таза; контрапост; какая сторона ближе к камере>

Руки и кисти:
<каждая рука отдельно: плечо, локоть, предплечье, запястье, кисть и пальцы;
сгибание; направление; касание; опора; скрытые части; что рука перекрывает>

Ноги и стопы:
<каждая нога отдельно: бедро, колено, голень, лодыжка и стопа; сгибание;
разведение или скрещивание; направление коленей и носков; видимость и сокращение>

Опоры и баланс:
<точки контакта с полом, мебелью, стеной, предметом или другим телом; несущая
конечность; центр тяжести; устойчивость; распределение веса>

Контакты и перекрытия:
<фактические касания между людьми и предметами; кто находится спереди; какие
части тела перекрыты; что видно частично; без домысливания скрытой анатомии>

Ракурс и кадрирование:
<высота и направление камеры; фронтальный, боковой, верхний или нижний ракурс;
перспективное сокращение; границы кадра; какие конечности обрезаны>

Готовый pose prompt:
<один плотный абзац на русском, пригодный для вставки в генератор; только поза,
ракурс, опоры, контакты и перекрытия; персонажи A/B обозначены однозначно>

Negative prompts:
<ошибки, специфичные для этой позы: wrong pose, mirrored pose, swapped limbs,
wrong hand placement, wrong contact points, wrong body overlap, floating body,
broken joints, extra limbs, missing limbs, fused hands, extra fingers, bad hands,
bad feet, duplicated person, incorrect perspective и другие релевантные ошибки>
""".strip()

_COMPACT_POSE_RETRY_INSTRUCTION = """
Проанализируй приложенное изображение заново и верни только полную техническую
карту позы. Не описывай внешность, одежду, сюжет, свет, палитру или интимную
анатомию. Не додумывай скрытые части тела. Соблюдай лево и право относительно
персонажа и точно укажи опоры, кисти, стопы, касания и перекрытия.

Используй строго этот порядок разделов и заполни каждый раздел:
Vᴇʟᴠᴇᴛ Pᴏsᴇ
Количество персонажей:
Общая схема позы:
Голова и шея:
Корпус и таз:
Руки и кисти:
Ноги и стопы:
Опоры и баланс:
Контакты и перекрытия:
Ракурс и кадрирование:
Готовый pose prompt:
Negative prompts:

Без кодового блока и без вводных фраз.
""".strip()


def _section_position(value: str, section: str) -> int:
    return value.casefold().find(section.casefold())


def _missing_pose_sections(value: str) -> tuple[str, ...]:
    return tuple(
        section
        for section in _POSE_SECTIONS
        if _section_position(value, section) < 0
    )


def _pose_sections_in_order(value: str) -> bool:
    positions = [_section_position(value, section) for section in _POSE_SECTIONS]
    return all(position >= 0 for position in positions) and positions == sorted(positions)


def _is_pose_complete(value: str) -> bool:
    return (
        len(value.strip()) >= 120
        and not _missing_pose_sections(value)
        and _pose_sections_in_order(value)
    )


def _better_pose_result(first: str, second: str) -> str:
    def score(value: str) -> tuple[int, int, int]:
        return (
            -len(_missing_pose_sections(value)),
            int(_pose_sections_in_order(value)),
            len(value),
        )

    return max((first, second), key=score)


class PoseExtractorClient(ImageToPromptClient):
    """Extract a reusable pose-only description from one source image."""

    async def generate(self, source: bytes) -> str:
        await self._ensure_vision_capability()
        prepared = await asyncio.to_thread(_prepare_image, source)
        image_base64 = base64.b64encode(prepared).decode("ascii")

        result, payload = await self._request(
            self._messages(image_base64, _POSE_EXTRACTION_INSTRUCTION),
            max_tokens=2600,
        )
        if not _is_pose_complete(result):
            retry, retry_payload = await self._request(
                self._messages(image_base64, _COMPACT_POSE_RETRY_INSTRUCTION),
                max_tokens=2200,
            )
            result = _better_pose_result(result, retry)
            if result == retry:
                payload = retry_payload

        if len(result) < 40:
            raise VisionAnalysisError(
                "Qwen вернул пустое или слишком короткое описание позы"
                + self._empty_diagnostic(payload)
                + "."
            )

        missing = _missing_pose_sections(result)
        if missing or not _pose_sections_in_order(result):
            detail = ", ".join(missing) if missing else "нарушен порядок разделов"
            raise VisionAnalysisError(
                "Qwen не смог вернуть полную карту позы: " + detail + "."
            )
        return result[:24000]


__all__ = (
    "POSE_EXTRACTOR_MARKER",
    "PoseExtractorClient",
    "_POSE_EXTRACTION_INSTRUCTION",
    "_is_pose_complete",
    "_missing_pose_sections",
    "_pose_sections_in_order",
)
