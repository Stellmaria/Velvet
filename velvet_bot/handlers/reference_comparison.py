from __future__ import annotations

import asyncio
import io
import json
import logging
from html import escape

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
)
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from velvet_bot.core.config import load_settings
from velvet_bot.database import Character, Database
from velvet_bot.handlers.reference_albums import parse_reference_selector
from velvet_bot.local_ai_runtime import get_local_ai_lock
from velvet_bot.reference_catalog import CharacterReference, list_character_references
from velvet_bot.reference_comparison import ReferenceComparisonClient
from velvet_bot.reference_comparison_repository import _save_report

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_TIMEOUT_SECONDS = 90
_RETRY_DELAYS = (1.0, 3.0)


def _result_file(message: Message) -> tuple[str, str | None] | None:
    source = message.reply_to_message or message
    if source.photo:
        photo = source.photo[-1]
        return photo.file_id, photo.file_unique_id
    if source.document and (source.document.mime_type or "").startswith("image/"):
        return source.document.file_id, source.document.file_unique_id
    return None


async def _resolve_reference(
    database: Database,
    raw_value: str,
) -> tuple[Character | None, CharacterReference | None, int, int]:
    cleaned = " ".join(raw_value.split()).strip()
    if not cleaned:
        return None, None, 0, 0

    character: Character | None
    try:
        character = await database.get_character(cleaned)
    except ValueError:
        character = None

    selected_index = 1
    if character is None:
        character_name, parsed_index = parse_reference_selector(cleaned)
        selected_index = parsed_index or 1
        try:
            character = await database.get_character(character_name)
        except ValueError:
            character = None

    if character is None:
        return None, None, selected_index, 0

    references = await list_character_references(database, character.id, limit=50)
    total = len(references)
    if selected_index < 1 or selected_index > total:
        return character, None, selected_index, total
    return character, references[selected_index - 1], selected_index, total


async def _download_file(bot: Bot, file_id: str) -> bytes:
    errors: list[BaseException] = []
    for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
        try:
            destination = io.BytesIO()
            await bot.download(
                file_id,
                destination=destination,
                timeout=_DOWNLOAD_TIMEOUT_SECONDS,
                seek=True,
            )
            value = destination.getvalue()
            if value:
                return value
            errors.append(RuntimeError("Telegram вернул пустой файл."))
        except asyncio.CancelledError:
            raise
        except TelegramBadRequest as error:
            errors.append(error)
            break
        except (TelegramNetworkError, TimeoutError, ConnectionError, OSError) as error:
            errors.append(error)
            if attempt >= _DOWNLOAD_ATTEMPTS:
                break
            await asyncio.sleep(_RETRY_DELAYS[attempt - 1])
        except TelegramAPIError as error:
            errors.append(error)
            break
    if errors:
        raise RuntimeError(f"Не удалось скачать изображение: {errors[-1]}")
    raise RuntimeError("Telegram вернул пустой файл.")


def _list_block(title: str, values: object, emoji: str) -> list[str]:
    if not isinstance(values, list) or not values:
        return []
    lines = ["", f"<b>{emoji} {escape(title)}</b>"]
    for value in values[:8]:
        lines.append(f"• {escape(str(value))}")
    return lines


def _format_report(
    *,
    report_id: int,
    character: Character,
    reference_index: int,
    reference_total: int,
    report: dict[str, object],
) -> str:
    verdict = str(report.get("verdict") or "partial")
    verdict_label = {
        "strong": "высокое визуальное соответствие",
        "partial": "частичное соответствие",
        "weak": "заметные расхождения",
        "insufficient": "недостаточно видимых деталей",
    }.get(verdict, verdict)
    verdict_emoji = {
        "strong": "✅",
        "partial": "⚠️",
        "weak": "🚨",
        "insufficient": "🔎",
    }.get(verdict, "⚠️")

    lines = [
        f"<b>{verdict_emoji} Сравнение с референсом #{report_id}</b>",
        "",
        f"Персонаж: <b>{escape(character.name)}</b>",
        f"Референс: <b>{reference_index}</b> из <b>{reference_total}</b>",
        f"Вердикт: <b>{escape(verdict_label)}</b>",
        f"Общее соответствие: <b>{int(report.get('overall_score') or 0)} / 100</b>",
        f"Уверенность Qwen: <b>{int(report.get('confidence') or 0)}%</b>",
        "",
        f"Лицо: <b>{int(report.get('face_score') or 0)} / 100</b>",
        f"Волосы: <b>{int(report.get('hair_score') or 0)} / 100</b>",
        f"Телосложение: <b>{int(report.get('body_score') or 0)} / 100</b>",
        f"Уникальные признаки: <b>{int(report.get('unique_traits_score') or 0)} / 100</b>",
        "",
        f"<b>Итог:</b> {escape(str(report.get('summary_ru') or '—'))}",
    ]
    lines.extend(_list_block("Совпадения лица", report.get("face_matches"), "✅"))
    lines.extend(_list_block("Расхождения лица", report.get("face_differences"), "⚠️"))
    lines.extend(_list_block("Совпадения волос", report.get("hair_matches"), "✅"))
    lines.extend(_list_block("Расхождения волос", report.get("hair_differences"), "⚠️"))
    lines.extend(_list_block("Совпадения телосложения", report.get("body_matches"), "✅"))
    lines.extend(_list_block("Расхождения телосложения", report.get("body_differences"), "⚠️"))
    lines.extend(_list_block("Совпавшие уникальные признаки", report.get("unique_matches"), "✅"))
    lines.extend(_list_block("Различия уникальных признаков", report.get("unique_differences"), "⚠️"))
    lines.extend(_list_block("Недостаточно видно", report.get("uncertain_areas"), "🔎"))

    visibility = report.get("visibility")
    if isinstance(visibility, dict):
        lines.extend(
            [
                "",
                "<b>Видимость для проверки:</b>",
                (
                    "• лицо: референс "
                    f"<b>{int(visibility.get('reference_face') or 0)}%</b>, "
                    f"результат <b>{int(visibility.get('result_face') or 0)}%</b>"
                ),
                (
                    "• тело: референс "
                    f"<b>{int(visibility.get('reference_body') or 0)}%</b>, "
                    f"результат <b>{int(visibility.get('result_body') or 0)}%</b>"
                ),
            ]
        )
    lines.extend(
        [
            "",
            "Qwen оценивает только визуальное соответствие видимых черт. "
            "Это не установление личности человека.",
        ]
    )
    return "\n".join(lines)[:4090]


@router.message(Command("compare_ref", "compare_reference"))
async def handle_reference_comparison(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
) -> None:
    if message.chat.type != ChatType.PRIVATE:
        await message.answer("Сравнение внешности доступно в личном чате с ботом.")
        return
    if not command.args:
        await message.answer(
            "Ответьте этой командой на готовое изображение и укажите персонажа.\n\n"
            "Пример: <code>/compare_ref Каэль 2</code>"
        )
        return

    result_file = _result_file(message)
    if result_file is None:
        await message.answer(
            "Команду нужно отправить ответом на фотографию или изображение-документ.\n\n"
            "Пример: <code>/compare_ref Каэль 1</code>"
        )
        return

    character, reference, reference_index, reference_total = await _resolve_reference(
        database,
        command.args,
    )
    if character is None:
        await message.answer("Такой персонаж не найден.")
        return
    if reference is None:
        if reference_total == 0:
            await message.answer(
                f"У персонажа <b>{escape(character.name)}</b> пока нет референсов."
            )
        else:
            await message.answer(
                f"У персонажа <b>{escape(character.name)}</b> только "
                f"<b>{reference_total}</b> референс(а/ов)."
            )
        return

    settings = load_settings()
    if not settings.ai_vision_enabled:
        await message.answer("Локальный Qwen сейчас отключён в настройках бота.")
        return

    status = await message.answer(
        f"🔎 Сравниваю результат с референсом <b>{reference_index}</b> "
        f"персонажа <b>{escape(character.name)}</b>…\n"
        "Проверяю лицо, волосы, телосложение и уникальные видимые признаки."
    )
    result_file_id, result_unique_id = result_file
    try:
        reference_bytes, result_bytes = await asyncio.gather(
            _download_file(bot, reference.telegram_file_id),
            _download_file(bot, result_file_id),
        )
        client = ReferenceComparisonClient(
            provider=settings.ai_vision_provider,
            base_url=settings.ai_vision_base_url,
            model=settings.ai_vision_model,
            api_key=settings.ai_vision_api_key,
            timeout_seconds=settings.ai_vision_timeout_seconds,
        )
        async with get_local_ai_lock():
            report = await client.compare(reference_bytes, result_bytes)
        report_id = await _save_report(
            database,
            character_id=character.id,
            reference_id=reference.id,
            result_file_id=result_file_id,
            result_file_unique_id=result_unique_id,
            provider=client.provider,
            model=client.model,
            report=report,
            created_by=message.from_user.id if message.from_user else None,
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.exception(
            "Reference comparison failed character_id=%s reference_id=%s",
            character.id,
            reference.id,
        )
        await status.edit_text(
            "❌ Сравнение не завершено. Ошибка отправлена в центр инцидентов.\n\n"
            f"<code>{escape(str(error))[:900]}</code>"
        )
        return

    await status.edit_text(
        _format_report(
            report_id=report_id,
            character=character,
            reference_index=reference_index,
            reference_total=reference_total,
            report=report,
        )
    )


__all__ = ("router",)
