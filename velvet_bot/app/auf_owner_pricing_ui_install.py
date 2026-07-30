from __future__ import annotations

import importlib
from html import escape

from aiogram.types import Message

from velvet_bot.domains.auf_wallet import (
    AufPricingRepository,
    AufWalletStatus,
    format_auf_units,
    format_owner_price_details,
)

_INSTALLED = False


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
    quote = await AufPricingRepository(database).quote(
        {
            "workspace_id": workspace_id,
            "request": request.to_task_payload(),
        }
    )
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
    available_units = overview.wallet.available_units
    enough = global_owner or available_units >= quote.quoted_units
    remaining_units = max(0, available_units - quote.quoted_units)
    ratio = "как у исходника" if request.aspect_ratio == "auto" else request.aspect_ratio

    if global_owner:
        wallet_line = (
            f"Учётная цена: <b>{format_auf_units(quote.quoted_units, max_places=0)}</b>\n"
            "Списание Стэл: <b>0 вельветов</b>"
        )
    elif enough:
        wallet_line = (
            f"Цена: <b>{format_auf_units(quote.quoted_units, max_places=0)}</b>\n"
            f"Доступно: <b>{format_auf_units(available_units)}</b>\n"
            f"Останется: <b>{format_auf_units(remaining_units)}</b>"
        )
    else:
        missing = quote.quoted_units - available_units
        wallet_line = (
            f"Цена: <b>{format_auf_units(quote.quoted_units, max_places=0)}</b>\n"
            f"Доступно: <b>{format_auf_units(available_units)}</b>\n"
            f"Не хватает: <b>{format_auf_units(missing)}</b>"
        )

    owner_block = (
        f"\n\n{format_owner_price_details(quote)}" if global_owner else ""
    )
    await state.set_state(photo_ui.photo_router.AufPhotoForm.confirming_generation)
    await photo_ui.edit_or_answer_auf_callback(
        callback,
        text=(
            "<b>Проверьте перед созданием</b>\n\n"
            f"Модель: <b>{escape(request.model.display_name)}</b>\n"
            f"Фото: <b>{len(request.references)}</b> из "
            f"{request.model.max_photo_references}\n"
            f"Качество: <b>{escape(request.resolution)}</b>\n"
            f"Соотношение: <b>{escape(ratio)}</b>\n"
            "Результат: <b>1 изображение</b>\n"
            "Контент: <b>Mature</b>\n\n"
            f"<b>Стоимость в вельветах</b>\n{wallet_line}"
            f"{owner_block}\n\n"
            f"<b>Текст</b>\n{escape(photo_ui.photo_router._truncate(request.prompt, 2200))}\n\n"
            "<i>Цена фиксируется при подтверждении. Если себестоимость, курс или "
            "тариф изменятся до запуска, бот попросит подтвердить новую сумму.</i>"
        ),
        reply_markup=photo_ui._final_keyboard(
            workspace_id=workspace_id,
            model=request.model,
            quoted_units=quote.quoted_units,
        ),
    )


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
            {"workspace_id": workspace_id, "request": request.to_task_payload()}
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
    wallet_lines, can_submit = portal._wallet_lines(
        wallet=overview.wallet,
        quoted_units=quote.quoted_units,
        global_owner=global_owner,
    )
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
    lines.extend(["", "<b>Стоимость в вельветах</b>", *wallet_lines])
    if global_owner:
        lines.extend(["", format_owner_price_details(quote)])
    lines.extend(
        [
            "",
            f"<b>Движение и сцена</b>\n{escape(portal.video_core.truncate_text(prompt, 3500))}",
            "",
            "<i>Цена фиксируется при подтверждении. Если себестоимость, курс или "
            "тариф изменятся до резервирования, бот попросит подтвердить новую сумму.</i>",
        ]
    )
    await state.set_state(portal.video_router.AufVideoForm.reviewing)
    await portal.video_core.edit_or_answer(
        callback,
        text="\n".join(lines),
        reply_markup=portal._video_review_keyboard(
            workspace_id=workspace_id,
            quoted_units=quote.quoted_units,
            can_submit=can_submit,
        ),
    )


async def _render_wallet(
    callback,
    *,
    workspace_id: int,
    wallet_service,
    purchase_service,
    answer_callback: bool = True,
) -> None:
    wallet_router = importlib.import_module(
        "velvet_bot.presentation.telegram.routers.workspace_auf_wallet"
    )
    try:
        overview = await wallet_service.overview(
            workspace_id=workspace_id,
            actor_user_id=callback.from_user.id,
            history_limit=8,
        )
        quotes = await wallet_service.package_quotes(
            workspace_id=workspace_id,
            actor_user_id=callback.from_user.id,
        )
        invoices = await purchase_service.recent_invoices(
            workspace_id=workspace_id,
            actor_user_id=callback.from_user.id,
            limit=5,
        )
    except (PermissionError, ValueError) as error:
        if answer_callback:
            await callback.answer(str(error), show_alert=True)
        return

    global_owner = wallet_service.is_global_owner(callback.from_user.id)
    wallet = overview.wallet
    history = "\n".join(wallet_router._entry_line(item) for item in overview.recent_entries)
    packages = "\n".join(
        (
            f"• <b>{quote.amount_auf} вельветов</b> · {quote.price_rub:.0f} ₽"
            + (
                f" · ${quote.price_usd:.2f} · {quote.price_byn:.2f} Br"
                if global_owner
                else ""
            )
        )
        for quote in quotes
    )
    invoice_lines = "\n".join(wallet_router._invoice_line(item) for item in invoices)
    internal = ""
    if global_owner:
        settings = await wallet_service.economy_settings(
            actor_user_id=callback.from_user.id
        )
        nominal_rub = settings.retail_auf_usd * settings.billing_usd_to_rub
        nominal_byn = settings.retail_auf_usd * settings.billing_usd_to_byn
        internal = (
            "\n\n<b>Служебная экономика · только Стэл</b>\n"
            f"Наценка к себестоимости провайдера: <b>{settings.retail_markup_percent}%</b>\n"
            f"Курс: <b>$1 · {settings.billing_usd_to_rub} ₽ РФ · "
            f"{settings.billing_usd_to_byn} Br</b>\n"
            f"Номинал 1 вельвета: <b>${settings.retail_auf_usd} · "
            f"{nominal_rub:.2f} ₽ РФ · {nominal_byn:.2f} Br</b>\n"
            "Списание генераций округляется вверх до целого вельвета."
        )
    text = (
        "<b>💳 Кошелёк вельветов</b>\n\n"
        f"Доступно: <b>{format_auf_units(wallet.available_units)}</b>\n"
        f"В резерве: <b>{format_auf_units(wallet.reserved_units)}</b>\n"
        f"Потрачено за 30 дней: <b>{format_auf_units(overview.spent_30d_units)}</b>\n"
        f"Статус: <b>{'заморожен' if wallet.status is AufWalletStatus.FROZEN else 'активен'}</b>\n\n"
        "<b>Пакеты</b>\n"
        f"{packages}\n\n"
        "Нажмите пакет, чтобы создать заявку на пополнение. Цена фиксируется на 24 часа. "
        "После оплаты Стэл подтвердит заявку, и вельветы появятся на балансе.\n\n"
        "<b>Последние счета</b>\n"
        f"{invoice_lines or '• счетов пока нет'}\n\n"
        "<b>Последние операции</b>\n"
        f"{history or '• операций пока нет'}"
        f"{internal}"
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text,
            reply_markup=wallet_router._wallet_keyboard(
                workspace_id=workspace_id,
                global_owner=global_owner,
                frozen=wallet.status is AufWalletStatus.FROZEN,
                invoices=invoices,
            ),
        )
    if answer_callback:
        await callback.answer()


def install_auf_owner_pricing_ui() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    photo_ui = importlib.import_module("velvet_bot.app.auf_photo_ui_install")
    portal = importlib.import_module("velvet_bot.app.auf_user_portal_install")
    wallet_router = importlib.import_module(
        "velvet_bot.presentation.telegram.routers.workspace_auf_wallet"
    )
    photo_ui._show_auf_final = _show_photo_review
    portal._show_video_auf_review = _show_video_review
    wallet_router._render_wallet = _render_wallet
    _INSTALLED = True


__all__ = ("install_auf_owner_pricing_ui",)
