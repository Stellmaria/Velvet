from __future__ import annotations

import importlib
from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.domains.auf_wallet import (
    AufPricingRepository,
    AufWalletStatus,
    format_auf_units,
    format_owner_price_details,
    format_vl_units,
)
from velvet_bot.domains.media_generation import KieInputMode, KieModelAlias

_INSTALLED = False


def _copy_button(button, *, text: str):
    copy_method = getattr(button, "model_copy", None)
    if copy_method is None:
        copy_method = button.copy
    return copy_method(update={"text": text})


def _photo_keyboard(
    photo_ui,
    *,
    workspace_id: int,
    model,
    quoted_units: int,
    global_owner: bool,
) -> InlineKeyboardMarkup:
    base = photo_ui.photo_router._final_keyboard(workspace_id, model)
    rows = [list(row) for row in base.inline_keyboard]
    if rows and rows[0]:
        rows[0][0] = _copy_button(
            rows[0][0],
            text=(
                "Да, создать"
                if global_owner
                else f"Да, создать · {format_vl_units(quoted_units)}"
            ),
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _video_keyboard(
    portal,
    *,
    workspace_id: int,
    quoted_units: int,
    can_submit: bool,
    global_owner: bool,
) -> InlineKeyboardMarkup:
    if global_owner:
        first_text = "Запустить"
        first_action = "submit"
    elif can_submit:
        first_text = f"Запустить · {format_vl_units(quoted_units)}"
        first_action = "submit"
    else:
        first_text = "Пересчитать баланс и цену"
        first_action = "review"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=first_text,
                    callback_data=portal.video_router.video_callback(
                        first_action,
                        workspace_id=workspace_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Изменить параметры",
                    callback_data=portal.video_router.video_callback(
                        "settings", workspace_id=workspace_id
                    ),
                ),
                InlineKeyboardButton(
                    text="Изменить модель",
                    callback_data=portal.video_router.video_callback(
                        "models", workspace_id=workspace_id
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=portal.video_router.video_callback(
                        "cancel", workspace_id=workspace_id
                    ),
                )
            ],
        ]
    )


def _user_wallet_lines(*, wallet, quoted_units: int) -> tuple[list[str], bool]:
    price = format_vl_units(quoted_units)
    if wallet.status == AufWalletStatus.FROZEN:
        return ([f"Стоимость: <b>{price}</b>", "Кошелёк: <b>заморожен</b>"], False)
    if wallet.available_units >= quoted_units:
        return (
            [
                f"Стоимость: <b>{price}</b>",
                f"Доступно: <b>{format_auf_units(wallet.available_units)}</b>",
                "Останется: "
                f"<b>{format_auf_units(wallet.available_units - quoted_units)}</b>",
            ],
            True,
        )
    return (
        [
            f"Стоимость: <b>{price}</b>",
            f"Доступно: <b>{format_auf_units(wallet.available_units)}</b>",
            "Не хватает: "
            f"<b>{format_auf_units(quoted_units - wallet.available_units)}</b>",
        ],
        False,
    )


def _seedream_reference_notice(request) -> list[str]:
    if request.model is not KieModelAlias.SEEDREAM_5_PRO:
        return []
    return [
        "",
        "<b>Seedream и референсы</b>",
        "Итоговая стоимость зависит от количества референсов.",
        f"Сейчас в расчёте учтено: <b>{len(request.references)}</b>.",
    ]


def _result_count(request) -> int:
    try:
        return max(1, int(request.extra_input.get("n", 1)))
    except (TypeError, ValueError):
        return 1


def _result_label(count: int) -> str:
    last_two = count % 100
    last = count % 10
    if 11 <= last_two <= 14:
        word = "изображений"
    elif last == 1:
        word = "изображение"
    elif 2 <= last <= 4:
        word = "изображения"
    else:
        word = "изображений"
    return f"{count} {word}"


async def _show_photo_review(
    callback,
    state,
    *,
    database,
    wallet_service,
) -> None:
    photo_ui = importlib.import_module("velvet_bot.app.auf_photo_ui_install")
    data = await state.get_data()
    request = photo_ui.photo_router._request(data)
    workspace_id = int(photo_ui._state_value(data, "auf_workspace_id") or 0)
    quote_payload: dict[str, object] = {
        "workspace_id": workspace_id,
        "user_id": callback.from_user.id,
        "request": request.to_task_payload(),
    }
    quote = await AufPricingRepository(database).quote(quote_payload)
    await state.update_data(
        auf_expected_price_version=quote.version_key,
        auf_expected_quoted_units=quote.quoted_units,
    )
    overview = await wallet_service.overview(
        workspace_id=workspace_id,
        actor_user_id=callback.from_user.id,
        history_limit=1,
    )
    global_owner = wallet_service.is_global_owner(callback.from_user.id)
    ratio = "как у исходника" if request.aspect_ratio == "auto" else request.aspect_ratio
    count = _result_count(request)

    lines = [
        "<b>Проверьте перед созданием</b>",
        "",
        f"Модель: <b>{escape(request.model.display_name)}</b>",
        f"Режим: <b>{escape(request.input_mode.value)}</b>",
    ]
    if request.input_mode is KieInputMode.PHOTO_TEXT:
        lines.append(
            f"Референсы: <b>{len(request.references)}/{request.model.max_photo_references}</b>"
        )
    lines.extend(
        [
            f"Качество: <b>{escape(request.resolution)}</b>",
            f"Соотношение: <b>{escape(ratio)}</b>",
            f"Результат: <b>{_result_label(count)}</b>",
        ]
    )
    if request.model is KieModelAlias.WAN_27_IMAGE:
        lines.append(
            "Связная серия: "
            f"<b>{'включена' if request.extra_input.get('enable_sequential') else 'выключена'}</b>"
        )
    lines.append("Контент: <b>Mature</b>")

    if global_owner:
        can_submit = True
        lines.extend(["", format_owner_price_details(quote)])
    else:
        wallet_lines, can_submit = _user_wallet_lines(
            wallet=overview.wallet,
            quoted_units=quote.quoted_units,
        )
        lines.extend(["", "<b>Стоимость в VL</b>", *wallet_lines])
        lines.extend(_seedream_reference_notice(request))

    lines.extend(
        [
            "",
            f"<b>Текст</b>\n{escape(photo_ui.photo_router._truncate(request.prompt, 2200))}",
        ]
    )
    if not global_owner:
        lines.extend(
            [
                "",
                "<i>Цена фиксируется при подтверждении. Если итоговая стоимость "
                "изменится до запуска, бот попросит подтвердить новую сумму.</i>",
            ]
        )

    await state.set_state(photo_ui.photo_router.AufPhotoForm.confirming_generation)
    await photo_ui.edit_or_answer_auf_callback(
        callback,
        text="\n".join(lines),
        reply_markup=_photo_keyboard(
            photo_ui,
            workspace_id=workspace_id,
            model=request.model,
            quoted_units=quote.quoted_units,
            global_owner=global_owner,
        ),
    )
    if not can_submit and not global_owner:
        return


async def _show_video_review(
    callback,
    *,
    state,
    workspace_id: int,
    database,
    wallet_service,
) -> None:
    portal = importlib.import_module("velvet_bot.app.auf_user_portal_install")
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
        overview = await wallet_service.overview(
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
    global_owner = wallet_service.is_global_owner(callback.from_user.id)
    lines = [
        "<b>Проверьте видео перед запуском</b>",
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
        lines.append(f"Звук: <b>{'включён' if generate_audio else 'выключен'}</b>")
    if model == "wan":
        lines.append(f"Кадры: <b>{portal.video_router.wan_mode_name(wan_mode)}</b>")

    if global_owner:
        can_submit = True
        lines.extend(["", format_owner_price_details(quote)])
    else:
        wallet_lines, can_submit = _user_wallet_lines(
            wallet=overview.wallet,
            quoted_units=quote.quoted_units,
        )
        lines.extend(["", "<b>Стоимость в VL</b>", *wallet_lines])

    lines.extend(
        [
            "",
            f"<b>Движение и сцена</b>\n{escape(portal.video_core.truncate_text(prompt, 3500))}",
        ]
    )
    if not global_owner:
        lines.extend(
            [
                "",
                "<i>Цена фиксируется при подтверждении. Если итоговая стоимость "
                "изменится до резервирования, бот попросит подтвердить новую сумму.</i>",
            ]
        )

    await state.set_state(portal.video_router.AufVideoForm.reviewing)
    await portal.video_core.edit_or_answer(
        callback,
        text="\n".join(lines),
        reply_markup=_video_keyboard(
            portal,
            workspace_id=workspace_id,
            quoted_units=quote.quoted_units,
            can_submit=can_submit,
            global_owner=global_owner,
        ),
    )


def install_auf_generation_price_privacy() -> None:
    """Install final generation screens with strict owner/user price privacy."""

    global _INSTALLED
    if _INSTALLED:
        return
    owner_ui = importlib.import_module("velvet_bot.app.auf_owner_pricing_ui_install")
    photo_ui = importlib.import_module("velvet_bot.app.auf_photo_ui_install")
    portal = importlib.import_module("velvet_bot.app.auf_user_portal_install")

    owner_ui._show_photo_review = _show_photo_review
    owner_ui._show_video_review = _show_video_review
    photo_ui._show_auf_final = _show_photo_review
    portal._show_video_auf_review = _show_video_review
    _INSTALLED = True


__all__ = ("install_auf_generation_price_privacy",)
