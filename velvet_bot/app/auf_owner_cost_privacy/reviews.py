from __future__ import annotations

from html import escape
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.app.auf_owner_cost_privacy.formatting import (
    is_global_owner,
    owner_cost_block,
)
from velvet_bot.domains.auf_wallet import AufPricingRepository


def _owner_video_keyboard(portal: Any, *, workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Запустить",
                    callback_data=portal.video_router.video_callback(
                        "submit",
                        workspace_id=workspace_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Изменить параметры",
                    callback_data=portal.video_router.video_callback(
                        "settings",
                        workspace_id=workspace_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="Изменить модель",
                    callback_data=portal.video_router.video_callback(
                        "models",
                        workspace_id=workspace_id,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=portal.video_router.video_callback(
                        "cancel",
                        workspace_id=workspace_id,
                    ),
                )
            ],
        ]
    )


def install_owner_review_screens(photo_ui: Any, portal: Any) -> None:
    original_photo_review = photo_ui._show_auf_final
    original_video_review = portal._show_video_auf_review

    async def show_photo_review(
        callback: Any,
        state: Any,
        *,
        database: Any,
        wallet_service: Any,
    ) -> None:
        if not is_global_owner(callback.from_user.id):
            await original_photo_review(
                callback,
                state,
                database=database,
                wallet_service=wallet_service,
            )
            return

        data = await state.get_data()
        request = photo_ui.photo_router._request(data)
        workspace_id = int(photo_ui._state_value(data, "auf_workspace_id") or 0)
        quote = await AufPricingRepository(database).quote(
            {
                "workspace_id": workspace_id,
                "user_id": callback.from_user.id,
                "request": request.to_task_payload(),
            }
        )
        await wallet_service.overview(
            workspace_id=workspace_id,
            actor_user_id=callback.from_user.id,
            history_limit=1,
        )
        await state.update_data(
            auf_expected_price_version=quote.version_key,
            auf_expected_quoted_units=quote.quoted_units,
        )
        ratio = (
            "как у исходника"
            if request.aspect_ratio == "auto"
            else request.aspect_ratio
        )
        await state.set_state(
            photo_ui.photo_router.AufPhotoForm.confirming_generation
        )
        await photo_ui.edit_or_answer_auf_callback(
            callback,
            text=(
                "<b>Проверьте перед созданием · Стэл</b>\n\n"
                f"Модель: <b>{escape(request.model.display_name)}</b>\n"
                f"Фото: <b>{len(request.references)}</b> из "
                f"{request.model.max_photo_references}\n"
                f"Качество: <b>{escape(request.resolution)}</b>\n"
                f"Соотношение: <b>{escape(ratio)}</b>\n"
                "Результат: <b>1 изображение</b>\n\n"
                f"{owner_cost_block(quote)}\n\n"
                f"<b>Текст</b>\n"
                f"{escape(photo_ui.photo_router._truncate(request.prompt, 2200))}"
                "\n\n<i>Показана себестоимость провайдера до общей и "
                "индивидуальной наценки. Коммерческая цена пользователя здесь "
                "не применяется.</i>"
            ),
            reply_markup=photo_ui.photo_router._final_keyboard(
                workspace_id,
                request.model,
            ),
        )

    async def show_video_review(
        callback: Any,
        *,
        state: Any,
        workspace_id: int,
        database: Any,
        wallet_service: Any,
    ) -> None:
        if not is_global_owner(callback.from_user.id):
            await original_video_review(
                callback,
                state=state,
                workspace_id=workspace_id,
                database=database,
                wallet_service=wallet_service,
            )
            return

        try:
            (
                request,
                prompt,
                model,
                resolution,
                duration,
                generate_audio,
                wan_mode,
            ) = portal._video_request_from_state(await state.get_data())
            quote = await AufPricingRepository(database).quote(
                {
                    "workspace_id": workspace_id,
                    "user_id": callback.from_user.id,
                    "request": request.to_task_payload(),
                }
            )
            await wallet_service.overview(
                workspace_id=workspace_id,
                actor_user_id=callback.from_user.id,
                history_limit=1,
            )
        except (PermissionError, ValueError, RuntimeError) as error:
            await callback.answer(str(error), show_alert=True)
            return

        await state.update_data(
            auf_video_expected_price_version=quote.version_key,
            auf_video_expected_quoted_units=quote.quoted_units,
        )
        lines = [
            "<b>Проверьте видео перед запуском · Стэл</b>",
            "",
            f"Модель: <b>{escape(portal.video_router.MODEL_NAMES[model])}</b>",
            f"Разрешение: <b>{escape(resolution)}</b>",
            (
                "Длительность: <b>автоматически, расчёт 6 сек</b>"
                if model == "grok"
                else f"Длительность: <b>{duration} сек</b>"
            ),
        ]
        if model == "seedance":
            lines.append(
                f"Звук: <b>{'включён' if generate_audio else 'выключен'}</b>"
            )
        if model == "wan":
            lines.append(
                f"Кадры: <b>{portal.video_router.wan_mode_name(wan_mode)}</b>"
            )
        lines.extend(
            [
                "",
                owner_cost_block(quote),
                "",
                f"<b>Движение и сцена</b>\n"
                f"{escape(portal.video_core.truncate_text(prompt, 3500))}",
                "",
                "<i>Показана себестоимость провайдера до общей и "
                "индивидуальной наценки. Коммерческая цена пользователя здесь "
                "не применяется.</i>",
            ]
        )
        await state.set_state(portal.video_router.AufVideoForm.reviewing)
        await portal.video_core.edit_or_answer(
            callback,
            text="\n".join(lines),
            reply_markup=_owner_video_keyboard(
                portal,
                workspace_id=workspace_id,
            ),
        )

    photo_ui._show_auf_final = show_photo_review
    portal._show_video_auf_review = show_video_review


__all__ = ("install_owner_review_screens",)
