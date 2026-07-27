from __future__ import annotations

import asyncio
import logging
from html import escape
from typing import Any, Awaitable, Callable

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.core.config import load_settings
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.qwen_repository import WorkspaceQwenRepository
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.image_to_prompt import ImageToPromptClient
from velvet_bot.local_ai_runtime import get_local_ai_lock

logger = logging.getLogger(__name__)


class WorkspaceImagePromptForm(StatesGroup):
    image = State()


def _render_result(job_id: int, prompt: str) -> str:
    escaped = escape(prompt)
    if len(escaped) > 3600:
        escaped = escaped[:3600].rstrip() + "\n\n…полный текст приложен файлом."
    return (
        "<b>🪄 Qwen · изображение в промт</b>\n\n"
        f"Задание: <b>#{job_id}</b>\n\n"
        f"<pre>{escaped}</pre>"
    )[:4090]


async def handle_workspace_image_prompt(
    message: Message,
    state: FSMContext,
    database: Database,
    bot,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    from velvet_bot.presentation.telegram import workspace_qwen

    context = await workspace_qwen._require_form_context(
        message,
        state,
        workspace_service,
        workspace_product_service,
    )
    if context is None:
        return
    workspace, _, _ = context
    image_file = workspace_qwen._message_image(message)
    if image_file is None:
        await message.answer("Нужно отправить фотографию или image-документ.")
        return

    file_id, unique_id = image_file
    settings = load_settings()
    repository = WorkspaceQwenRepository(database)
    job_id = await repository.create_job(
        workspace_id=workspace.id,
        kind="image_to_prompt",
        title="Изображение в промт",
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
        created_by=message.from_user.id if message.from_user else None,
        request_payload={
            "image_file_id": file_id,
            "image_file_unique_id": unique_id,
        },
    )
    status = await message.answer(
        f"<b>🪄 Qwen-задание #{job_id}</b>\n\nСкачиваю и анализирую изображение…"
    )
    try:
        await repository.set_job_stage(job_id, "downloading")
        image = await workspace_qwen._download_image(bot, file_id)
        await repository.set_job_stage(job_id, "analyzing")
        client = ImageToPromptClient(
            provider=settings.ai_vision_provider,
            base_url=settings.ai_vision_base_url,
            model=settings.ai_vision_model,
            api_key=settings.ai_vision_api_key,
            timeout_seconds=settings.ai_vision_timeout_seconds,
        )
        async with get_local_ai_lock():
            prompt = await client.generate(image)
        rendered = _render_result(job_id, prompt)
        await repository.finish_job(
            job_id=job_id,
            result_text=rendered,
            result_payload={"prompt": prompt},
        )
        await message.answer_document(
            BufferedInputFile(
                prompt.encode("utf-8"),
                filename=f"qwen-image-prompt-{job_id}.txt",
            ),
            caption="Полный image-to-prompt без ограничения длины сообщения Telegram",
        )
        await status.edit_text(
            rendered,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="↩️ Qwen",
                            callback_data=workspace_qwen.qwen_callback(
                                "menu", workspace_id=workspace.id
                            ),
                        )
                    ]
                ]
            ),
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:  # p2-approved-boundary: workspace-qwen-image-to-prompt
        logger.exception("Workspace image-to-prompt failed workspace_id=%s", workspace.id)
        await repository.fail_job(job_id=job_id, error=error)
        await status.edit_text(
            "❌ Qwen не создал промт.\n\n"
            f"<code>{escape(str(error))[:1200]}</code>"
        )
    finally:
        await state.clear()


def install_image_to_prompt_ui() -> None:
    from velvet_bot.presentation.telegram import workspace_qwen

    if getattr(workspace_qwen, "_image_to_prompt_installed", False):
        return

    original_menu = workspace_qwen._menu_keyboard
    original_callback = workspace_qwen.handle_workspace_qwen_callback
    original_register = workspace_qwen.register_workspace_qwen
    original_job_label = workspace_qwen._job_label

    def menu_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
        markup = original_menu(workspace_id)
        rows = [list(row) for row in markup.inline_keyboard]
        insert_at = max(0, len(rows) - 2)
        rows.insert(
            insert_at,
            [
                InlineKeyboardButton(
                    text="🪄 Изображение → промт",
                    callback_data=workspace_qwen.qwen_callback(
                        "image_prompt", workspace_id=workspace_id
                    ),
                )
            ],
        )
        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def callback_handler(
        callback: CallbackQuery,
        callback_data,
        state: FSMContext,
        workspace_service: WorkspaceService,
        workspace_product_service: WorkspaceProductService,
        database: Database,
    ) -> None:
        if callback_data.action != "image_prompt":
            await original_callback(
                callback,
                callback_data,
                state,
                workspace_service,
                workspace_product_service,
                database,
            )
            return
        try:
            workspace, _ = await workspace_qwen._require_qwen_context(
                workspace_service=workspace_service,
                workspace_product_service=workspace_product_service,
                user_id=callback.from_user.id,
                workspace_id=callback_data.workspace_id,
            )
        except WorkspaceAccessError as error:
            await callback.answer(str(error), show_alert=True)
            return
        await state.set_state(WorkspaceImagePromptForm.image)
        await state.update_data(workspace_id=workspace.id)
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "<b>🪄 Изображение → промт</b>\n\n"
                "Отправьте изображение как фото или image-файл. "
                "Qwen восстановит подробный основной и negative prompt."
            )
        await callback.answer()

    def register(router: Router) -> None:
        original_register(router)
        router.message.register(
            handle_workspace_image_prompt,
            WorkspaceImagePromptForm.image,
            F.photo | F.document,
        )

    def job_label(job) -> str:
        if job.kind == "image_to_prompt":
            return "Изображение → промт"
        return original_job_label(job)

    workspace_qwen._menu_keyboard = menu_keyboard
    workspace_qwen.handle_workspace_qwen_callback = callback_handler
    workspace_qwen.register_workspace_qwen = register
    workspace_qwen._job_label = job_label
    workspace_qwen._image_to_prompt_installed = True


__all__ = ("WorkspaceImagePromptForm", "install_image_to_prompt_ui")
