from __future__ import annotations

import asyncio
import importlib
import logging
from collections.abc import Mapping
from html import escape
from uuid import UUID

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.domains.media_generation.file_delivery_worker import (
    _DEFAULT_RESULT_USER_AGENT,
    _RESULT_DOWNLOAD_TIMEOUT_SECONDS,
    _RESULT_MAX_BYTES,
    _download_result_http,
    _result_filename,
)
from velvet_bot.domains.media_generation.friendly_worker import FriendlyKieGenerationWorker
from velvet_bot.domains.media_generation.models import (
    KIE_GENERATION_TASK_TYPE,
    KieGenerationRequest,
    KieTaskRecord,
)
from velvet_bot.presentation.telegram.routers.workspace_auf import AufCallback

logger = logging.getLogger(__name__)
_INSTALLED = False
_TELEGRAM_RETRY_ATTEMPTS = 4


def _mapping(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _result_urls(value: object) -> tuple[str, ...]:
    result = _mapping(value)
    urls = result.get("result_urls")
    if not isinstance(urls, (list, tuple)):
        return ()
    return tuple(str(item).strip() for item in urls if str(item).strip())


def _delivery_callback(*, workspace_id: int, task_id: UUID) -> str:
    return AufCallback(
        action="deliver",
        workspace_id=int(workspace_id),
        value=str(task_id),
    ).pack()


async def _send_bot_with_retry(operation_name: str, operation):
    errors: list[TelegramAPIError] = []
    for attempt in range(1, _TELEGRAM_RETRY_ATTEMPTS + 1):
        try:
            return await operation()
        except asyncio.CancelledError:
            raise
        except TelegramBadRequest:
            raise
        except TelegramAPIError as error:
            errors.append(error)
            if attempt >= _TELEGRAM_RETRY_ATTEMPTS:
                break
            logger.warning(
                "Telegram result redelivery retry operation=%s attempt=%s/%s: %s",
                operation_name,
                attempt + 1,
                _TELEGRAM_RETRY_ATTEMPTS,
                error,
            )
            await asyncio.sleep(min(8, 2 ** max(0, attempt - 1)))
    if errors:
        raise errors[-1]
    raise RuntimeError(f"Telegram operation {operation_name} did not execute.")


async def _send_downloaded_result(
    *,
    bot,
    chat_id: int,
    request: KieGenerationRequest,
    record: KieTaskRecord,
    url: str,
    index: int,
    payload: bytes,
    mime_type: str | None,
    caption: str | None,
) -> tuple[bool, bool]:
    filename = _result_filename(
        url=url,
        provider_task_id=record.task_id,
        index=index,
        mime_type=mime_type,
        video=request.model.is_video,
    )
    document_sent = False
    preview_sent = False

    document_caption = "Оригинальный файл без сжатия Telegram."
    if caption:
        document_caption = f"{caption}\n\n{document_caption}"
    try:
        await _send_bot_with_retry(
            "stored result document",
            lambda: bot.send_document(
                chat_id,
                document=BufferedInputFile(payload, filename=filename),
                caption=document_caption,
                disable_content_type_detection=True,
            ),
        )
        document_sent = True
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Stored result document delivery failed task=%s", record.task_id)

    try:
        if request.model.is_video:
            await _send_bot_with_retry(
                "stored result video preview",
                lambda: bot.send_video(
                    chat_id,
                    video=BufferedInputFile(payload, filename=filename),
                    caption=("Предпросмотр результата." if document_sent else caption),
                    supports_streaming=True,
                ),
            )
        else:
            await _send_bot_with_retry(
                "stored result image preview",
                lambda: bot.send_photo(
                    chat_id,
                    photo=BufferedInputFile(payload, filename=filename),
                    caption=("Предпросмотр результата." if document_sent else caption),
                ),
            )
        preview_sent = True
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Stored result preview delivery failed task=%s", record.task_id)

    return document_sent, preview_sent


async def _send_direct_url_fallback(
    *,
    bot,
    chat_id: int,
    request: KieGenerationRequest,
    record: KieTaskRecord,
    url: str,
    caption: str | None,
    error: BaseException,
) -> bool:
    fallback_caption = (
        (f"{caption}\n\n" if caption else "")
        + "Бот не смог скачать оригинал с CDN провайдера, поэтому отправляет "
        "результат напрямую по сохранённому URL. Новая генерация не запускалась."
    )
    direct_sent = False
    try:
        if request.model.is_video:
            await _send_bot_with_retry(
                "direct result video",
                lambda: bot.send_video(
                    chat_id,
                    video=url,
                    caption=fallback_caption,
                    supports_streaming=True,
                ),
            )
        else:
            await _send_bot_with_retry(
                "direct result image",
                lambda: bot.send_photo(
                    chat_id,
                    photo=url,
                    caption=fallback_caption,
                ),
            )
        direct_sent = True
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Direct result URL delivery failed task=%s", record.task_id)

    lines = [
        "<b>Генерация завершена, но оригинальный файл не скачался</b>",
        "",
        f"Задача провайдера: <code>{escape(record.task_id)}</code>",
        "Новая платная генерация не запускалась.",
    ]
    if direct_sent:
        lines.append("Предпросмотр отправлен напрямую по URL провайдера.")
    else:
        lines.extend(
            [
                "Telegram также не смог получить файл напрямую.",
                f'<a href="{escape(url, quote=True)}">Открыть сохранённый результат</a>',
            ]
        )
    lines.extend(("", f"Ошибка доставки: <code>{escape(str(error)[:500])}</code>"))
    try:
        await _send_bot_with_retry(
            "result delivery warning",
            lambda: bot.send_message(chat_id, "\n".join(lines)),
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Could not report result delivery failure task=%s", record.task_id)
    return direct_sent


def _result_caption(
    request: KieGenerationRequest,
    record: KieTaskRecord,
    *,
    provider: str,
) -> str:
    media_name = "Видео" if request.model.is_video else "Изображение"
    return (
        f"<b>Ауф · {escape(request.model.display_name)}</b>\n"
        f"Провайдер: <b>{escape(provider)}</b>\n"
        f"{media_name}: <b>готово</b>\n"
        f"Качество: <b>{escape(request.resolution)}</b>\n"
        f"Референсов: <b>{len(request.references)}</b>\n"
        f"Задача провайдера: <code>{escape(record.task_id)}</code>"
    )


async def _deliver_record_with_recovery(
    self: FriendlyKieGenerationWorker,
    *,
    chat_id: int | None,
    request: KieGenerationRequest,
    record: KieTaskRecord,
) -> None:
    if chat_id is None:
        return
    provider = "GRS AI" if request.model.is_grs else "Kie.ai"
    caption = _result_caption(request, record, provider=provider)
    if not record.result_urls:
        await self._send_telegram_with_retry(
            "empty result notice",
            lambda: self._bot.send_message(
                chat_id,
                caption
                + "\n\nПровайдер завершил задачу без URL результата. "
                "Повторная платная генерация не запускалась.",
            ),
        )
        return

    for index, url in enumerate(record.result_urls, start=1):
        item_caption = caption if index == 1 else None
        try:
            result = await self._download_result(url)
            filename = _result_filename(
                url=url,
                provider_task_id=record.task_id,
                index=index,
                mime_type=result.mime_type,
                video=request.model.is_video,
            )
            if request.model.is_video:
                await self._send_video_and_document(
                    chat_id=chat_id,
                    payload=result.payload,
                    filename=filename,
                    caption=item_caption,
                )
            else:
                await self._send_image_and_document(
                    chat_id=chat_id,
                    payload=result.payload,
                    filename=filename,
                    caption=item_caption,
                )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception(
                "%s task %s succeeded but result delivery failed url=%s",
                provider,
                record.task_id,
                url,
            )
            await _send_direct_url_fallback(
                bot=self._bot,
                chat_id=chat_id,
                request=request,
                record=record,
                url=url,
                caption=item_caption,
                error=error,
            )


async def _load_owned_success_task(
    database,
    *,
    task_id: UUID,
    workspace_id: int,
    actor_user_id: int,
):
    async with database.acquire() as connection:
        return await connection.fetchrow(
            """
            SELECT id, payload, result
            FROM ai_tasks
            WHERE id = $1::UUID
              AND task_type = $2::VARCHAR
              AND status = 'success'
              AND created_by = $3::BIGINT
              AND payload ->> 'workspace_id' = $4::TEXT
            """,
            task_id,
            KIE_GENERATION_TASK_TYPE,
            int(actor_user_id),
            str(int(workspace_id)),
        )


async def _redeliver_user_task(
    callback,
    *,
    database,
    workspace_id: int,
    task_id_text: str,
) -> None:
    try:
        task_id = UUID(task_id_text)
    except (TypeError, ValueError):
        await callback.answer("Некорректный ID задачи.", show_alert=True)
        return

    row = await _load_owned_success_task(
        database,
        task_id=task_id,
        workspace_id=workspace_id,
        actor_user_id=callback.from_user.id,
    )
    if row is None:
        await callback.answer(
            "Готовая задача не найдена или принадлежит другому пользователю.",
            show_alert=True,
        )
        return

    payload = _mapping(row["payload"])
    request_payload = _mapping(payload.get("request"))
    try:
        request = KieGenerationRequest.from_task_payload(request_payload)
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return

    result = _mapping(row["result"])
    urls = _result_urls(result)
    if not urls:
        await callback.answer("У задачи нет сохранённого URL результата.", show_alert=True)
        return

    provider_task_id = str(result.get("provider_task_id") or task_id).strip()
    from velvet_bot.domains.media_generation.models import KieTaskState

    record = KieTaskRecord(
        task_id=provider_task_id,
        state=KieTaskState.SUCCESS,
        result_urls=urls,
    )
    chat_id = (
        int(callback.message.chat.id)
        if getattr(callback, "message", None) is not None
        else int(callback.from_user.id)
    )
    await callback.answer("Повторяю доставку без новой генерации.")
    caption = _result_caption(
        request,
        record,
        provider=("GRS AI" if request.model.is_grs else "Kie.ai"),
    )

    delivered = 0
    for index, url in enumerate(urls, start=1):
        item_caption = caption if index == 1 else None
        try:
            downloaded = await asyncio.to_thread(
                _download_result_http,
                url,
                timeout_seconds=_RESULT_DOWNLOAD_TIMEOUT_SECONDS,
                max_bytes=_RESULT_MAX_BYTES,
                user_agent=_DEFAULT_RESULT_USER_AGENT,
            )
            document_sent, preview_sent = await _send_downloaded_result(
                bot=callback.bot,
                chat_id=chat_id,
                request=request,
                record=record,
                url=url,
                index=index,
                payload=downloaded.payload,
                mime_type=downloaded.mime_type,
                caption=item_caption,
            )
            if document_sent or preview_sent:
                delivered += 1
                continue
            raise RuntimeError("Telegram не принял ни оригинал, ни предпросмотр.")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if await _send_direct_url_fallback(
                bot=callback.bot,
                chat_id=chat_id,
                request=request,
                record=record,
                url=url,
                caption=item_caption,
                error=error,
            ):
                delivered += 1

    if delivered:
        await callback.bot.send_message(
            chat_id,
            f"Повторная доставка завершена: <b>{delivered}/{len(urls)}</b>. "
            "Новая платная генерация не запускалась.",
        )
    else:
        await callback.bot.send_message(
            chat_id,
            "Не удалось повторно доставить сохранённый результат. "
            "URL задачи сохранён, новая генерация не запускалась.",
        )


async def _result_map(database, task_ids: list[UUID]) -> dict[UUID, object]:
    if not task_ids:
        return {}
    async with database.acquire() as connection:
        rows = await connection.fetch(
            "SELECT id, result FROM ai_tasks WHERE id = ANY($1::UUID[])",
            task_ids,
        )
    return {row["id"]: row["result"] for row in rows}


def _task_delivery_buttons(
    *,
    portal,
    page,
    results: Mapping[UUID, object],
    workspace_id: int,
) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    for row in page:
        if str(row["status"]) != "success":
            continue
        urls = _result_urls(results.get(row["id"]))
        if not urls:
            continue
        request = _mapping(_mapping(row["payload"]).get("request"))
        model_alias = str(request.get("model") or "").strip()
        model = portal._MODEL_NAMES.get(model_alias, model_alias or "Результат")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📤 Доставить · {model}"[:60],
                    callback_data=_delivery_callback(
                        workspace_id=workspace_id,
                        task_id=row["id"],
                    ),
                )
            ]
        )
    return rows


async def _render_user_tasks_with_delivery(
    callback,
    *,
    state,
    database,
    workspace_id: int,
    offset: int,
) -> None:
    portal = importlib.import_module("velvet_bot.app.auf_user_portal_install")
    await state.clear()
    rows = await portal._load_user_tasks(
        database,
        workspace_id=workspace_id,
        actor_user_id=callback.from_user.id,
        offset=offset,
    )
    page = rows[: portal._TASK_PAGE_SIZE]
    results = await _result_map(database, [row["id"] for row in page])
    text = (
        "<b>🧾 Мои задачи Ауф</b>\n\n"
        "Для готовых задач доступна повторная доставка сохранённого результата. "
        "Она не запускает модель повторно и ничего не списывает.\n\n"
        + (
            "\n\n".join(portal._task_line(row) for row in page)
            if page
            else "• задач пока нет"
        )
    )
    base = portal._task_list_keyboard(
        workspace_id=workspace_id,
        offset=offset,
        has_next=len(rows) > portal._TASK_PAGE_SIZE,
    )
    delivery_rows = _task_delivery_buttons(
        portal=portal,
        page=page,
        results=results,
        workspace_id=workspace_id,
    )
    await portal.video_core._edit_or_answer(
        callback,
        text=text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[*delivery_rows, *base.inline_keyboard]
        ),
    )


def install_auf_result_delivery_recovery() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    portal = importlib.import_module("velvet_bot.app.auf_user_portal_install")
    controller = importlib.import_module(
        "velvet_bot.presentation.telegram.workspace_home_controller"
    )
    original_action = controller.handle_scoped_auf_action

    async def handle_scoped_auf_delivery_action(
        callback,
        callback_data,
        state,
        access_policy,
        kie_settings,
        database,
        ai_usage_service,
        ai_task_queue_service,
        auf_runtime_service,
        auf_wallet_service,
        auf_purchase_service,
    ) -> None:
        if callback_data.action != "deliver":
            await original_action(
                callback,
                callback_data,
                state,
                access_policy,
                kie_settings,
                database,
                ai_usage_service,
                ai_task_queue_service,
                auf_runtime_service,
                auf_wallet_service,
                auf_purchase_service,
            )
            return
        if not await controller._require_auf_callback(
            callback,
            workspace_id=callback_data.workspace_id,
            service=auf_runtime_service,
        ):
            return
        await _redeliver_user_task(
            callback,
            database=database,
            workspace_id=int(callback_data.workspace_id),
            task_id_text=str(callback_data.value or ""),
        )

    FriendlyKieGenerationWorker._deliver_best_effort = _deliver_record_with_recovery
    portal._render_user_tasks = _render_user_tasks_with_delivery
    controller.handle_scoped_auf_action = handle_scoped_auf_delivery_action
    _INSTALLED = True


__all__ = (
    "install_auf_result_delivery_recovery",
    "_deliver_record_with_recovery",
    "_delivery_callback",
)
