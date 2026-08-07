from __future__ import annotations

import importlib
from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Any
from uuid import UUID

from velvet_bot.application.media_tasks import task_payload_mapping
from velvet_bot.domains.auf_wallet import (
    AufInsufficientBalance,
    AufPriceNotConfigured,
    AufWalletFrozen,
    format_auf_units,
)
from velvet_bot.domains.media_generation.models import (
    KieGenerationRequest,
    KieTaskRecord,
)
from velvet_bot.infrastructure.media_delivery_runtime import redeliver_owned_task

_INSTALLED = False


@dataclass(frozen=True, slots=True)
class AufGenerationReceipt:
    task_id: UUID | None = None
    elapsed_seconds: int | None = None
    successful_attempt: int | None = None
    quoted_units: int = 0
    captured_units: int = 0
    charge_status: str = ""


def _row_value(row: Any, key: str, default: object = None) -> object:
    try:
        value = row[key]
    except (KeyError, TypeError, IndexError):
        return default
    return default if value is None else value


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(str(value or "0").strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _non_negative_int(value: object) -> int:
    try:
        return max(0, int(str(value or "0").strip()))
    except (TypeError, ValueError):
        return 0


def _elapsed_seconds(created_at: object, completed_at: object) -> int | None:
    if not isinstance(created_at, datetime) or not isinstance(completed_at, datetime):
        return None
    created = created_at
    completed = completed_at
    if created.tzinfo is None and completed.tzinfo is not None:
        created = created.replace(tzinfo=completed.tzinfo)
    elif completed.tzinfo is None and created.tzinfo is not None:
        completed = completed.replace(tzinfo=created.tzinfo)
    try:
        return max(0, int((completed - created).total_seconds() + 0.5))
    except TypeError:
        return None


def receipt_from_task_row(row: Any) -> AufGenerationReceipt:
    payload = task_payload_mapping(_row_value(row, "payload", {}))
    result = task_payload_mapping(_row_value(row, "result", {}))
    attempt = (
        _positive_int(result.get("provider_attempt_count"))
        or _positive_int(result.get("successful_attempt"))
        or _positive_int(result.get("attempt_count"))
        or _positive_int(_row_value(row, "attempt_count"))
    )
    quoted_units = _non_negative_int(
        _row_value(
            row,
            "quoted_units",
            payload.get("auf_expected_quoted_units"),
        )
    )
    captured_units = _non_negative_int(_row_value(row, "captured_units", 0))
    charge_status = str(_row_value(row, "charge_status", "") or "").strip()
    if charge_status == "captured" and captured_units <= 0:
        captured_units = quoted_units
    task_id_value = _row_value(row, "id")
    task_id = task_id_value if isinstance(task_id_value, UUID) else None
    return AufGenerationReceipt(
        task_id=task_id,
        elapsed_seconds=_elapsed_seconds(
            _row_value(row, "created_at"),
            _row_value(row, "completed_at"),
        ),
        successful_attempt=attempt,
        quoted_units=quoted_units,
        captured_units=captured_units,
        charge_status=charge_status,
    )


def format_generation_elapsed(seconds: int | None) -> str:
    if seconds is None:
        return "не сохранено"
    safe = max(0, int(seconds))
    if safe < 1:
        return "менее 1 сек"
    hours, remainder = divmod(safe, 3600)
    minutes, secs = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours} ч")
    if minutes:
        parts.append(f"{minutes} мин")
    if secs or not parts:
        parts.append(f"{secs} сек")
    return " ".join(parts)


def build_public_result_caption(
    request: KieGenerationRequest,
    receipt: AufGenerationReceipt | None,
) -> str:
    media_name = "Видео" if request.model.is_video else "Изображение"
    lines = [
        f"<b>Ауф · {escape(request.model.display_name)}</b>",
        f"{media_name}: <b>готово</b>",
        f"Качество: <b>{escape(request.resolution)}</b>",
        f"Референсов: <b>{len(request.references)}</b>",
    ]
    if receipt is not None:
        lines.append(
            "Время генерации: "
            f"<b>{escape(format_generation_elapsed(receipt.elapsed_seconds))}</b>"
        )
        if receipt.successful_attempt is not None:
            lines.append(f"Успешная попытка: <b>{receipt.successful_attempt}</b>")
        if receipt.charge_status == "captured":
            lines.append(f"Списано: <b>{format_auf_units(receipt.captured_units)}</b>")
        elif receipt.quoted_units > 0:
            lines.append("Списание: <b>0 вельветов · служебная генерация</b>")
    return "\n".join(lines)


def append_receipt_to_task_card(text: str, row: Any) -> str:
    if str(_row_value(row, "status", "")) != "success":
        return text
    receipt = receipt_from_task_row(row)
    lines = [
        f"Время генерации: <b>{escape(format_generation_elapsed(receipt.elapsed_seconds))}</b>"
    ]
    if receipt.successful_attempt is not None:
        lines.append(f"Успешная попытка: <b>{receipt.successful_attempt}</b>")
    addition = "\n".join(lines)
    marker = "\n\nНажмите"
    if marker in text:
        return text.replace(marker, f"\n{addition}{marker}", 1)
    return f"{text}\n{addition}"


def append_receipt_to_task_line(text: str, row: Any) -> str:
    if str(_row_value(row, "status", "")) != "success":
        return text
    receipt = receipt_from_task_row(row)
    details = [f"время {format_generation_elapsed(receipt.elapsed_seconds)}"]
    if receipt.successful_attempt is not None:
        details.append(f"попытка {receipt.successful_attempt}")
    return f"{text}\n  {escape(' · '.join(details))}"


async def deliver_record_with_receipt(
    self: Any,
    *,
    chat_id: int | None,
    request: KieGenerationRequest,
    record: KieTaskRecord,
) -> None:
    """Reject the retired worker hook; durable delivery owns successful results."""
    del self, chat_id, request, record
    raise RuntimeError(
        "Legacy receipt delivery hook is retired; durable media delivery owns results"
    )


async def redeliver_user_task_with_receipt(
    callback: Any,
    *,
    database: Any,
    workspace_id: int,
    task_id_text: str,
) -> None:
    """Compatibility entry point delegated to canonical durable redelivery."""
    await redeliver_owned_task(
        callback,
        database=database,
        workspace_id=workspace_id,
        task_id_text=task_id_text,
    )


def _install_photo_charge_guard() -> None:
    photo_ui = importlib.import_module("velvet_bot.app.auf_photo_ui_install")
    original = getattr(photo_ui, "_enqueue_auf_photo", None)
    if not callable(original) or getattr(original, "__auf_charge_guard__", False):
        return

    async def guarded(*args: Any, **kwargs: Any) -> None:
        callback = args[0] if args else kwargs.get("callback")
        try:
            await original(*args, **kwargs)
        except (
            AufInsufficientBalance,
            AufWalletFrozen,
            AufPriceNotConfigured,
            ValueError,
            RuntimeError,
        ) as error:
            if callback is None:
                raise
            await callback.answer(str(error), show_alert=True)

    guarded.__auf_charge_guard__ = True  # type: ignore[attr-defined]
    photo_ui._enqueue_auf_photo = guarded


def install_auf_generation_receipts() -> None:
    """Install receipt-only UI decoration without taking delivery ownership."""
    global _INSTALLED
    if _INSTALLED:
        return
    portal = importlib.import_module("velvet_bot.app.auf_user_portal_install")
    original_line = portal.format_user_task_line
    if not getattr(original_line, "__auf_receipt_wrapped__", False):

        def line_with_receipt(row: Any) -> str:
            return append_receipt_to_task_line(original_line(row), row)

        line_with_receipt.__auf_receipt_wrapped__ = True  # type: ignore[attr-defined]
        portal.format_user_task_line = line_with_receipt

    _install_photo_charge_guard()
    _INSTALLED = True


__all__ = (
    "AufGenerationReceipt",
    "append_receipt_to_task_card",
    "append_receipt_to_task_line",
    "build_public_result_caption",
    "deliver_record_with_receipt",
    "format_generation_elapsed",
    "install_auf_generation_receipts",
    "receipt_from_task_row",
    "redeliver_user_task_with_receipt",
)
