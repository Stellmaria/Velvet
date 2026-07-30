from __future__ import annotations

import contextvars
import importlib
import logging
import re
from decimal import Decimal
from html import escape
from typing import Any

from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID

logger = logging.getLogger(__name__)
_INSTALLED = False
_OWNER_DELIVERY: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "auf_owner_delivery",
    default=False,
)
_ATTEMPT_LINE = re.compile(r"^.*(?:Успешная попытка|Попытка|Повтор):.*$", re.MULTILINE)
_INLINE_ATTEMPT = re.compile(r"\s*·\s*попытка\s+\d+", re.IGNORECASE)
_OWNER_VELVET_LINE = re.compile(
    r"^.*(?:Учётная цена|Списание Стэл|Зарезервировано):.*$",
    re.MULTILINE,
)


def _is_owner_id(value: object) -> bool:
    try:
        return int(value or 0) == GLOBAL_WORKSPACE_CREATOR_ID
    except (TypeError, ValueError):
        return False


def _is_owner_task(task: object) -> bool:
    return _is_owner_id(getattr(task, "created_by", None))


def _row_value(row: Any, key: str, default: object = None) -> object:
    try:
        value = row[key]
    except (KeyError, TypeError, IndexError):
        return default
    return default if value is None else value


def _row_is_owner(row: Any) -> bool:
    return _is_owner_id(_row_value(row, "created_by"))


def _compact_decimal(value: Decimal) -> str:
    rendered = f"{value.quantize(Decimal('0.01')):.2f}".rstrip("0").rstrip(".")
    return rendered or "0"


def _money_triplet(usd: Decimal, quote: Any) -> str:
    rub = usd * Decimal(quote.billing_usd_to_rub)
    byn = usd * Decimal(quote.billing_usd_to_byn)
    return f"<b>${usd:.4f}</b> · <b>{rub:.2f} ₽ РФ</b> · <b>{byn:.2f} Br</b>"


def format_owner_real_costs(quote: Any) -> str:
    """Render real provider economics without exposing internal velvet accounting."""

    provider_cost = Decimal(quote.provider_cost_usd)
    retail_cost = Decimal(quote.target_retail_usd)
    minimum_revenue = Decimal(quote.minimum_revenue_usd)
    minimum_profit = minimum_revenue - provider_cost
    actual_markup = (
        minimum_profit / provider_cost * Decimal("100")
        if provider_cost > 0
        else Decimal("0")
    )
    return (
        "<b>Реальные расходы · только Стэл</b>\n"
        f"Провайдер: <code>{escape(str(quote.provider).upper())}</code>\n"
        f"Спишет провайдер: {_money_triplet(provider_cost, quote)}\n"
        f"Цена пользователю +{_compact_decimal(Decimal(quote.markup_percent))}%: "
        f"{_money_triplet(retail_cost, quote)}\n"
        "Минимальная выручка после округления до целого вельвета: "
        f"{_money_triplet(minimum_revenue, quote)}\n"
        "Минимальная прибыль: "
        f"{_money_triplet(minimum_profit, quote)} · "
        f"{_compact_decimal(actual_markup)}%"
    )


def public_generation_stage(stage: str) -> str:
    """Reduce provider and retry internals to a stable user-facing status."""

    text = str(stage or "").strip()
    folded = text.casefold()
    if any(
        token in folded
        for token in (
            "ошиб",
            "не дала результат",
            "остановлен",
            "остановила",
            "исчерпан",
            "использованы все",
            "не подтвердил",
        )
    ):
        return "Ошибка генерации."
    if any(token in folded for token in ("готово", "завершил генерацию", "100%")):
        return "Генерация завершена."
    if any(
        token in folded
        for token in (
            "попытк",
            "polling",
            "отправка в",
            "принял",
            "возобновляем",
            "продолжаем",
        )
    ):
        return "Генерация выполняется."
    text = re.sub(r"\b(?:Kie\.ai|Kie|GRS AI)\b", "сервис", text)
    text = re.sub(r"\b\d+/\d+\b", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" :-")
    return text or "Генерация выполняется."


def _remove_attempt_details(text: str) -> str:
    cleaned = _ATTEMPT_LINE.sub("", str(text or ""))
    cleaned = _INLINE_ATTEMPT.sub("", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _remove_owner_velvet_details(text: str) -> str:
    cleaned = _OWNER_VELVET_LINE.sub("", str(text or ""))
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _copy_first_button(markup: InlineKeyboardMarkup, *, text: str) -> InlineKeyboardMarkup:
    rows = [list(row) for row in markup.inline_keyboard]
    if rows and rows[0]:
        button = rows[0][0]
        copy_method = getattr(button, "model_copy", None) or getattr(button, "copy")
        rows[0][0] = copy_method(update={"text": text})
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _install_progress_and_failure_privacy() -> None:
    friendly = importlib.import_module("velvet_bot.domains.media_generation.friendly_worker")
    worker_class = friendly.FriendlyKieGenerationWorker
    original_progress_text = worker_class._friendly_progress_text
    original_failure = worker_class._notify_terminal_failure_best_effort

    if not getattr(original_progress_text, "__auf_private__", False):
        def private_progress_text(
            self: Any,
            *,
            task: Any,
            request: Any,
            percent: int,
            stage: str,
        ) -> str:
            if _is_owner_task(task):
                provider = "GRS AI" if request.model.is_grs else "Kie.ai"
                attempt_label = (
                    f"Повтор: <b>{task.attempt_count}/{task.max_attempts}</b>"
                    if task.attempt_count > 1
                    else f"Попытка: <b>{task.attempt_count}/{task.max_attempts}</b>"
                )
                safe_percent = max(0, min(100, int(percent)))
                return (
                    f"<b>Ауф создаёт · {escape(request.model.display_name)}</b>\n\n"
                    f"<code>{friendly.render_progress_bar(safe_percent)}</code> "
                    f"<b>{safe_percent}%</b>\n"
                    f"✨ {escape(friendly.friendly_stage(request, stage))}\n\n"
                    f"Провайдер: <b>{provider}</b>\n"
                    f"Режим: <b>{escape(request.input_mode.display_name)}</b>\n"
                    f"Качество: <b>{escape(request.resolution)}</b>\n"
                    f"Референсы: <b>{len(request.references)}</b>\n"
                    f"Контент: <b>{escape(request.content_mode.display_name)}</b>\n\n"
                    f"{attempt_label}\n"
                    f"Задача: <code>{task.id}</code>"
                )
            safe_percent = max(0, min(100, int(percent)))
            return (
                f"<b>Ауф создаёт · {escape(request.model.display_name)}</b>\n\n"
                f"<code>{friendly.render_progress_bar(safe_percent)}</code> "
                f"<b>{safe_percent}%</b>\n"
                f"✨ {escape(public_generation_stage(stage))}\n\n"
                f"Режим: <b>{escape(request.input_mode.display_name)}</b>\n"
                f"Качество: <b>{escape(request.resolution)}</b>\n"
                f"Референсы: <b>{len(request.references)}</b>\n"
                f"Контент: <b>{escape(request.content_mode.display_name)}</b>"
            )

        private_progress_text.__auf_private__ = True  # type: ignore[attr-defined]
        worker_class._friendly_progress_text = private_progress_text

    if not getattr(original_failure, "__auf_private__", False):
        async def private_terminal_failure(self: Any, task: Any, error: Exception) -> None:
            if _is_owner_task(task):
                await original_failure(self, task, error)
                return
            logger.error(
                "Auf generation failed task=%s user_id=%s error_type=%s error=%s",
                getattr(task, "id", None),
                getattr(task, "created_by", None),
                type(error).__name__,
                error,
                exc_info=(type(error), error, error.__traceback__),
            )
            chat_id = friendly.optional_int(task.payload.get("chat_id"))
            if chat_id is None:
                return
            try:
                await self._bot.send_message(chat_id, "<b>Ошибка генерации</b>")
            except TelegramAPIError:
                logger.exception(
                    "Could not deliver generic generation failure task=%s",
                    getattr(task, "id", None),
                )
            finally:
                self._provider_balances.pop(str(task.id), None)

        private_terminal_failure.__auf_private__ = True  # type: ignore[attr-defined]
        worker_class._notify_terminal_failure_best_effort = private_terminal_failure


def _install_receipt_privacy() -> None:
    receipts = importlib.import_module("velvet_bot.app.auf_generation_receipt_install")
    recovery = importlib.import_module("velvet_bot.app.auf_result_delivery_recovery")
    workers = importlib.import_module("velvet_bot.app.workers")

    original_builder = receipts.build_public_result_caption
    original_delivery = receipts.deliver_record_with_receipt
    original_redelivery = receipts.redeliver_user_task_with_receipt
    original_card = receipts.append_receipt_to_task_card
    original_line = receipts.append_receipt_to_task_line

    if not getattr(original_builder, "__auf_private__", False):
        def private_builder(request: Any, receipt: Any) -> str:
            text = original_builder(request, receipt)
            if _OWNER_DELIVERY.get():
                return _remove_owner_velvet_details(text)
            return _remove_attempt_details(text)

        private_builder.__auf_private__ = True  # type: ignore[attr-defined]
        receipts.build_public_result_caption = private_builder

    async def private_delivery(
        self: Any,
        *,
        chat_id: int | None,
        request: Any,
        record: Any,
    ) -> None:
        token = _OWNER_DELIVERY.set(_is_owner_id(chat_id))
        try:
            await original_delivery(self, chat_id=chat_id, request=request, record=record)
        finally:
            _OWNER_DELIVERY.reset(token)

    async def private_redelivery(callback: Any, **kwargs: Any) -> None:
        token = _OWNER_DELIVERY.set(_is_owner_id(callback.from_user.id))
        try:
            await original_redelivery(callback, **kwargs)
        finally:
            _OWNER_DELIVERY.reset(token)

    workers.KieGenerationWorker.install_delivery_handler(private_delivery)
    recovery.install_redelivery_handler(private_redelivery)

    if not getattr(original_card, "__auf_private__", False):
        def private_card(text: str, row: Any) -> str:
            rendered = original_card(text, row)
            return rendered if _row_is_owner(row) else _remove_attempt_details(rendered)

        private_card.__auf_private__ = True  # type: ignore[attr-defined]
        receipts.append_receipt_to_task_card = private_card

    if not getattr(original_line, "__auf_private__", False):
        def private_line(text: str, row: Any) -> str:
            rendered = original_line(text, row)
            return rendered if _row_is_owner(row) else _remove_attempt_details(rendered)

        private_line.__auf_private__ = True  # type: ignore[attr-defined]
        receipts.append_receipt_to_task_line = private_line


def _install_owner_real_money_reviews() -> None:
    owner_ui = importlib.import_module("velvet_bot.app.auf_owner_pricing_ui_install")
    photo_ui = importlib.import_module("velvet_bot.app.auf_photo_ui_install")
    portal = importlib.import_module("velvet_bot.app.auf_user_portal_install")

    original_photo_review = photo_ui._show_auf_final
    original_video_review = portal._show_video_auf_review

    async def owner_photo_review(
        callback: Any,
        state: Any,
        *,
        database: Any,
        wallet_service: Any,
    ) -> None:
        if not wallet_service.is_global_owner(callback.from_user.id):
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
        quote = await owner_ui.AufPricingRepository(database).quote(
            {"workspace_id": workspace_id, "request": request.to_task_payload()}
        )
        await state.update_data(
            auf_expected_price_version=quote.version_key,
            auf_expected_quoted_units=quote.quoted_units,
        )
        ratio = "как у исходника" if request.aspect_ratio == "auto" else request.aspect_ratio
        logger.info(
            "Auf owner price preview provider=%s model=%s provider_cost_usd=%s "
            "provider_cost_rub=%s provider_cost_byn=%s target_retail_usd=%s",
            quote.provider,
            quote.model_alias,
            quote.provider_cost_usd,
            quote.provider_cost_rub,
            quote.provider_cost_byn,
            quote.target_retail_usd,
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
                f"{format_owner_real_costs(quote)}\n\n"
                f"<b>Текст</b>\n"
                f"{escape(photo_ui.photo_router._truncate(request.prompt, 2200))}\n\n"
                "<i>Реальные расходы пересчитываются перед запуском по текущей "
                "себестоимости и курсам.</i>"
            ),
            reply_markup=photo_ui.photo_router._final_keyboard(
                workspace_id,
                request.model,
            ),
        )

    async def owner_video_review(
        callback: Any,
        *,
        state: Any,
        workspace_id: int,
        database: Any,
        wallet_service: Any,
    ) -> None:
        if not wallet_service.is_global_owner(callback.from_user.id):
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
            quote = await owner_ui.AufPricingRepository(database).quote(
                {"workspace_id": workspace_id, "request": request.to_task_payload()}
            )
        except (PermissionError, ValueError, RuntimeError) as error:
            await callback.answer(str(error), show_alert=True)
            return
        await state.update_data(
            auf_video_expected_price_version=quote.version_key,
            auf_video_expected_quoted_units=quote.quoted_units,
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
        lines.extend(
            [
                "",
                format_owner_real_costs(quote),
                "",
                f"<b>Движение и сцена</b>\n"
                f"{escape(portal.video_core.truncate_text(prompt, 3500))}",
                "",
                "<i>Реальные расходы пересчитываются перед запуском по текущей "
                "себестоимости и курсам.</i>",
            ]
        )
        await state.set_state(portal.video_router.AufVideoForm.reviewing)
        markup = portal._video_review_keyboard(
            workspace_id=workspace_id,
            quoted_units=quote.quoted_units,
            can_submit=True,
        )
        await portal.video_core.edit_or_answer(
            callback,
            text="\n".join(lines),
            reply_markup=_copy_first_button(markup, text="Запустить"),
        )

    photo_ui._show_auf_final = owner_photo_review
    portal._show_video_auf_review = owner_video_review

    original_photo_edit = photo_ui.edit_or_answer_auf_callback
    if not getattr(original_photo_edit, "__auf_private__", False):
        async def private_photo_edit(callback: Any, *, text: str, **kwargs: Any) -> Any:
            if _is_owner_id(callback.from_user.id):
                text = _remove_owner_velvet_details(text)
            return await original_photo_edit(callback, text=text, **kwargs)

        private_photo_edit.__auf_private__ = True  # type: ignore[attr-defined]
        photo_ui.edit_or_answer_auf_callback = private_photo_edit

    original_video_edit = portal.video_core.edit_or_answer
    if not getattr(original_video_edit, "__auf_private__", False):
        async def private_video_edit(callback: Any, *, text: str, **kwargs: Any) -> Any:
            if _is_owner_id(callback.from_user.id):
                text = _remove_owner_velvet_details(text)
            return await original_video_edit(callback, text=text, **kwargs)

        private_video_edit.__auf_private__ = True  # type: ignore[attr-defined]
        portal.video_core.edit_or_answer = private_video_edit


def install_auf_generation_privacy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_progress_and_failure_privacy()
    _install_receipt_privacy()
    _install_owner_real_money_reviews()
    _INSTALLED = True


__all__ = (
    "format_owner_real_costs",
    "install_auf_generation_privacy",
    "public_generation_stage",
)
