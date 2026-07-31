from __future__ import annotations

import importlib
import re
from contextvars import ContextVar
from decimal import Decimal
from html import escape
from typing import Any, Callable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.domains.auf_wallet import AufPricingRepository
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID

_INSTALLED = False
_OWNER_QUEUE_COST: ContextVar[str | None] = ContextVar(
    "auf_owner_queue_cost",
    default=None,
)
_ATTEMPT_LINE_RE = re.compile(
    r"(?mi)^(?:Попытка|Повтор|Успешная попытка):.*(?:\n|$)"
)


def _is_global_owner(user_id: object) -> bool:
    try:
        return int(user_id or 0) == int(GLOBAL_WORKSPACE_CREATOR_ID)
    except (TypeError, ValueError):
        return False


def _money(value: Decimal, places: int) -> str:
    return f"{Decimal(value):.{places}f}"


def _owner_cost_block_from_values(
    *,
    provider: str,
    usd: Decimal,
    rub: Decimal,
    byn: Decimal,
) -> str:
    return (
        "<b>Себестоимость провайдера · без наценки</b>\n"
        f"Маршрут: <code>{escape(str(provider).upper())}</code>\n"
        f"Списание: <b>${_money(usd, 4)}</b> · "
        f"<b>{_money(rub, 2)} ₽ РФ</b> · "
        f"<b>{_money(byn, 2)} Br</b>"
    )


def _owner_cost_block(quote: Any) -> str:
    return _owner_cost_block_from_values(
        provider=str(quote.provider),
        usd=Decimal(quote.provider_cost_usd),
        rub=Decimal(quote.provider_cost_rub),
        byn=Decimal(quote.provider_cost_byn),
    )


def _strip_attempt_details(text: str) -> str:
    """Remove retry counters from every product-facing result receipt."""

    return re.sub(r"\n{3,}", "\n\n", _ATTEMPT_LINE_RE.sub("", str(text))).strip()


def _rewrite_owner_queue_confirmation(text: str, cost_block: str) -> str:
    """Replace owner-only VL accounting lines with provider cost."""

    lines = str(text).splitlines()
    rewritten: list[str] = []
    inserted = False
    for line in lines:
        normalized = line.strip().casefold()
        is_price_line = normalized.startswith(
            (
                "зарезервировано:",
                "учётная цена:",
                "списание стэл:",
            )
        )
        if is_price_line:
            if not inserted:
                rewritten.extend(cost_block.splitlines())
                inserted = True
            continue
        rewritten.append(line)
    if not inserted:
        return str(text)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(rewritten)).strip()


def _progress_text_for_user(
    text: str,
    *,
    user_id: object,
    sanitizer: Callable[[str], str],
) -> str:
    if _is_global_owner(user_id):
        return str(text)
    return sanitizer(str(text))


def _install_owner_aware_progress_policy(brand_module: Any) -> None:
    """Teach the later privacy installer to preserve internal owner progress."""

    def wrap_progress_method(cls: type[Any]) -> None:
        original = getattr(cls, "_friendly_progress_text", None)
        if not callable(original) or getattr(original, "__auf_privacy_wrapped__", False):
            return

        def wrapped(
            self: Any,
            *,
            task: Any,
            request: Any,
            percent: int,
            stage: str,
        ) -> str:
            rendered = original(
                self,
                task=task,
                request=request,
                percent=percent,
                stage=stage,
            )
            payload = getattr(task, "payload", {})
            user_id = payload.get("user_id") if hasattr(payload, "get") else None
            return _progress_text_for_user(
                rendered,
                user_id=user_id,
                sanitizer=brand_module._sanitize_auf_text,
            )

        wrapped.__auf_privacy_wrapped__ = True  # type: ignore[attr-defined]
        cls._friendly_progress_text = wrapped  # type: ignore[method-assign]

    brand_module._wrap_progress_method = wrap_progress_method


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


def _install_owner_review_screens(photo_ui: Any, portal: Any) -> None:
    original_photo_review = photo_ui._show_auf_final
    original_video_review = portal._show_video_auf_review

    async def show_photo_review(
        callback: Any,
        state: Any,
        *,
        database: Any,
        wallet_service: Any,
    ) -> None:
        if not _is_global_owner(callback.from_user.id):
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
                f"{_owner_cost_block(quote)}\n\n"
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
        if not _is_global_owner(callback.from_user.id):
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
                _owner_cost_block(quote),
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


def _install_owner_queue_confirmations(photo_ui: Any, portal: Any) -> None:
    original_photo_edit = photo_ui.edit_or_answer_auf_callback
    original_video_edit = portal.video_core.edit_or_answer
    original_photo_enqueue = photo_ui._enqueue_auf_photo
    original_video_submit = portal._submit_video_with_auf

    async def photo_edit(callback: Any, *args: Any, **kwargs: Any) -> Any:
        cost_block = _OWNER_QUEUE_COST.get()
        text = kwargs.get("text")
        if (
            cost_block
            and _is_global_owner(callback.from_user.id)
            and isinstance(text, str)
        ):
            kwargs["text"] = _rewrite_owner_queue_confirmation(text, cost_block)
        return await original_photo_edit(callback, *args, **kwargs)

    async def video_edit(callback: Any, *args: Any, **kwargs: Any) -> Any:
        cost_block = _OWNER_QUEUE_COST.get()
        text = kwargs.get("text")
        if (
            cost_block
            and _is_global_owner(callback.from_user.id)
            and isinstance(text, str)
        ):
            kwargs["text"] = _rewrite_owner_queue_confirmation(text, cost_block)
        return await original_video_edit(callback, *args, **kwargs)

    async def enqueue_photo(
        callback: Any,
        state: Any,
        **kwargs: Any,
    ) -> Any:
        if not _is_global_owner(callback.from_user.id):
            return await original_photo_enqueue(callback, state, **kwargs)
        data = await state.get_data()
        request = photo_ui.photo_router._request(data)
        workspace_id = int(photo_ui._state_value(data, "auf_workspace_id") or 0)
        quote = await AufPricingRepository(kwargs["database"]).quote(
            {
                "workspace_id": workspace_id,
                "user_id": callback.from_user.id,
                "request": request.to_task_payload(),
            }
        )
        token = _OWNER_QUEUE_COST.set(_owner_cost_block(quote))
        try:
            return await original_photo_enqueue(callback, state, **kwargs)
        finally:
            _OWNER_QUEUE_COST.reset(token)

    async def submit_video(
        callback: Any,
        *,
        state: Any,
        workspace_id: int,
        kie_settings: Any,
        ai_usage_service: Any,
        ai_task_queue_service: Any,
        wallet_service: Any,
    ) -> Any:
        if not _is_global_owner(callback.from_user.id):
            return await original_video_submit(
                callback,
                state=state,
                workspace_id=workspace_id,
                kie_settings=kie_settings,
                ai_usage_service=ai_usage_service,
                ai_task_queue_service=ai_task_queue_service,
                wallet_service=wallet_service,
            )
        request, *_rest = portal._video_request_from_state(await state.get_data())
        usd = Decimal(kie_settings.pricing.estimate_usd(request))
        rub = Decimal(
            kie_settings.pricing.estimate_rub(
                request,
                usd_to_rub=kie_settings.usd_to_rub,
            )
        )
        settings = await wallet_service.economy_settings(
            actor_user_id=callback.from_user.id
        )
        byn = usd * Decimal(settings.billing_usd_to_byn)
        token = _OWNER_QUEUE_COST.set(
            _owner_cost_block_from_values(
                provider="kie",
                usd=usd,
                rub=rub,
                byn=byn,
            )
        )
        try:
            return await original_video_submit(
                callback,
                state=state,
                workspace_id=workspace_id,
                kie_settings=kie_settings,
                ai_usage_service=ai_usage_service,
                ai_task_queue_service=ai_task_queue_service,
                wallet_service=wallet_service,
            )
        finally:
            _OWNER_QUEUE_COST.reset(token)

    photo_ui.edit_or_answer_auf_callback = photo_edit
    portal.video_core.edit_or_answer = video_edit
    photo_ui._enqueue_auf_photo = enqueue_photo
    portal._submit_video_with_auf = submit_video


def _install_public_receipt_policy(receipt_module: Any) -> None:
    original = receipt_module.build_public_result_caption

    def build_public_result_caption(request: Any, receipt: Any) -> str:
        return _strip_attempt_details(original(request, receipt))

    receipt_module.build_public_result_caption = build_public_result_caption


def install_auf_owner_cost_privacy() -> None:
    """Separate public generation UI from creator-only provider economics."""

    global _INSTALLED
    if _INSTALLED:
        return

    photo_ui = importlib.import_module("velvet_bot.app.auf_photo_ui_install")
    portal = importlib.import_module("velvet_bot.app.auf_user_portal_install")
    receipt = importlib.import_module("velvet_bot.app.auf_generation_receipt_install")
    brand = importlib.import_module("velvet_bot.app.auf_grs_brand_install")

    _install_owner_review_screens(photo_ui, portal)
    _install_owner_queue_confirmations(photo_ui, portal)
    _install_public_receipt_policy(receipt)
    _install_owner_aware_progress_policy(brand)
    _INSTALLED = True


__all__ = (
    "_owner_cost_block_from_values",
    "_progress_text_for_user",
    "_rewrite_owner_queue_confirmation",
    "_strip_attempt_details",
    "install_auf_owner_cost_privacy",
)
