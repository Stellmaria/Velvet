from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from aiogram import Bot

_INSTALLED = False
_ORIGINAL_BOT_CALL = Bot.__call__

# These fields contain protocol identifiers rather than user-facing copy. Branding
# or redaction would invalidate callback routing, Telegram file references, URLs,
# or chat ids.
_IDENTIFIER_FIELDS = frozenset(
    {
        "callback_data",
        "url",
        "file_id",
        "chat_id",
        "message_id",
        "inline_message_id",
        "business_connection_id",
        "parse_mode",
        "switch_inline_query",
        "switch_inline_query_current_chat",
        "switch_inline_query_chosen_chat",
        "copy_text",
    }
)
_INTERNAL_SETTING_RE = re.compile(
    r"\b(?:KIE|GRS|OLLAMA|AI_VISION|ROLEPLAY)_[A-Z0-9_]+\b"
)
_PROVIDER_URL_RE = re.compile(
    r"https?://[^\s<>]*(?:kie\.ai|grsai\.com)[^\s<>]*",
    flags=re.IGNORECASE,
)
_AUF_AMOUNT_RE = re.compile(r"(?<![\w])(?P<amount>\d+(?:[.,]\d+)?)\s+Ауф\b")


def _brand_auf_text(value: str) -> str:
    """Replace every user-facing spelling of the retired Meow brand."""

    return (
        value.replace("🐈 <b>Мяу</b>", "🐕 <b>Ауф</b>")
        .replace("🐈 Мяу", "🐕 Ауф")
        .replace("МЯУ", "АУФ")
        .replace("Мяу", "Ауф")
        .replace("мяу", "ауф")
        .replace("MEOW", "AUF")
        .replace("Meow", "Auf")
        .replace("meow", "auf")
    )


def _velvet_currency_word(raw_amount: str) -> str:
    try:
        amount = abs(Decimal(raw_amount.replace(",", ".")))
    except InvalidOperation:
        return "вельветов"
    if amount != amount.to_integral_value():
        return "вельвета"
    number = int(amount)
    if 11 <= number % 100 <= 14:
        return "вельветов"
    last_digit = number % 10
    if last_digit == 1:
        return "вельвет"
    if last_digit in {2, 3, 4}:
        return "вельвета"
    return "вельветов"


def _brand_velvet_currency_text(value: str) -> str:
    """Expose the wallet currency as velvets while keeping the Auf module name."""

    branded = str(value)
    exact_replacements = {
        "Точная цена в Ауф": "Точная цена в вельветах",
        "Стоимость в Ауф": "Стоимость в вельветах",
        "Цена Ауф устарела": "Цена в вельветах устарела",
        "Недостаточно Ауф": "Недостаточно вельветов",
        "без операции Ауф": "без списания вельветов",
        "списаний Ауф нет": "списаний вельветов нет",
        "Баланс Ауф": "Баланс вельветов",
        "баланс Ауф": "баланс вельветов",
        "Кошелёк Ауф": "Кошелёк вельветов",
        "Списание Ауф": "Списание вельветов",
        "одного Ауф": "одного вельвета",
        "начислит Ауф дважды": "начислит вельветы дважды",
    }
    for old, new in exact_replacements.items():
        branded = branded.replace(old, new)

    def replace_amount(match: re.Match[str]) -> str:
        raw_amount = match.group("amount")
        return f"{raw_amount} {_velvet_currency_word(raw_amount)}"

    return _AUF_AMOUNT_RE.sub(replace_amount, branded)


def _redact_public_technical_text(value: str) -> str:
    """Remove known infrastructure details from Telegram-visible text.

    The guard is deliberately pattern-based rather than replacing every mention of
    a provider globally: owner log chats still need useful diagnostics, while product
    screens must not expose routing, credentials, task ids, or raw transport errors.
    """

    cleaned = str(value)
    exact_replacements = {
        "Kie.ai выключен на сервере.": "Генерация сейчас недоступна.",
        "GRS AI не настроен на сервере.": "Этот режим генерации сейчас недоступен.",
        "Nano Banana 2/Pro требуют GRS_API_KEY на сервере.": (
            "Эти модели сейчас недоступны."
        ),
        "Создание фото через Kie.ai.": "Создание фото.",
        "Интерфейс установлен, но Kie.ai пока выключен на сервере.": (
            "Генерация сейчас недоступна."
        ),
        "CDN провайдера": "источника результата",
        "URL провайдера": "сохранённому адресу результата",
        "по URL провайдера": "по сохранённому адресу результата",
        "NSFW checker Kie: <b>выключен</b>": (
            "Проверка содержимого: <b>автоматически</b>"
        ),
        "У задачи не сохранился ID провайдера. Повторная генерация не запускалась.": (
            "Для этой задачи не сохранились данные повторной доставки. "
            "Новая генерация не запускалась."
        ),
        "Результат скачан ботом напрямую с Kie.ai.": (
            "Результат получен и подготовлен к отправке."
        ),
        "Результат скачан ботом напрямую с GRS AI.": (
            "Результат получен и подготовлен к отправке."
        ),
    }
    for old, new in exact_replacements.items():
        cleaned = cleaned.replace(old, new)

    cleaned = re.sub(
        r"(?mi)^Провайдер:\s*.*(?:\n|$)",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"(?mi)^Задача провайдера:\s*.*(?:\n|$)",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"(?mi)^Задача:\s*<code>[0-9a-f-]{16,}</code>\s*(?:\n|$)",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"(?mi)^Баланс\s+(?:GRS|Kie)(?:\s+после\s+остановки)?:.*(?:\n|$)",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"(?mi)^Ошибка доставки:\s*<code>.*?</code>\s*(?:\n|$)",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"(?mi)^Причина GRS AI:.*(?:\n|$)",
        "Причина: запрос не прошёл автоматическую проверку содержимого.\n",
        cleaned,
    )
    cleaned = re.sub(
        r"(?mi)Неверный model id[^\n]*",
        "Модель временно недоступна из-за ошибки настройки.",
        cleaned,
    )
    cleaned = re.sub(
        r"(?mi)^.*(?:нужно заполнить|требуют?)\s+[^\n]*(?:API_KEY|BASE_URL|model id)[^\n]*(?:\n|$)",
        "Генерация временно недоступна из-за внутренней настройки.\n",
        cleaned,
    )
    cleaned = re.sub(
        r"(?mi)Не удалось получить сохранённый результат у провайдера:[^\n]*",
        "Не удалось получить сохранённый результат. Технические подробности "
        "записаны в служебный журнал.",
        cleaned,
    )
    cleaned = re.sub(
        r"(?mi)Лимит\s+(?:Kie\.ai|GRS AI)\s+установлен:",
        "Лимит генерации установлен:",
        cleaned,
    )
    cleaned = re.sub(
        r"(?mi)^(?:Kie\.ai|GRS AI):\s*",
        "Генерация: ",
        cleaned,
    )
    cleaned = re.sub(
        r"(?mi)(?:Kie\.ai|GRS AI) завершил(?:а)? задачу без URL результата\. ?",
        "Сервис завершил задачу без доступного результата.",
        cleaned,
    )

    if "<b>РЛ-статус</b>" in cleaned or "Калибровка Qwen" in cleaned:
        cleaned = re.sub(
            r"(?mi)^(?:Провайдер|Модель):\s*<code>.*?</code>\s*(?:\n|$)",
            "",
            cleaned,
        )

    cleaned = _INTERNAL_SETTING_RE.sub("внутренняя настройка", cleaned)
    cleaned = _PROVIDER_URL_RE.sub("[внутренний адрес скрыт]", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _copy_model(value: Any, updates: Mapping[str, object]) -> Any:
    model_copy = getattr(value, "model_copy", None)
    if callable(model_copy):
        return model_copy(update=dict(updates))
    legacy_copy = getattr(value, "copy", None)
    if callable(legacy_copy):
        return legacy_copy(update=dict(updates))
    return value


def _brand_telegram_value(
    value: Any,
    *,
    depth: int = 0,
    field_name: str | None = None,
) -> Any:
    """Brand and redact visible strings without mutating Telegram identifiers."""

    if depth > 10:
        return value
    if isinstance(value, str):
        if field_name in _IDENTIFIER_FIELDS:
            return value
        return _redact_public_technical_text(
            _brand_velvet_currency_text(_brand_auf_text(value))
        )
    if isinstance(value, list):
        return [
            _brand_telegram_value(
                item,
                depth=depth + 1,
                field_name=field_name,
            )
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _brand_telegram_value(
                item,
                depth=depth + 1,
                field_name=field_name,
            )
            for item in value
        )
    if isinstance(value, Mapping):
        return {
            key: _brand_telegram_value(
                item,
                depth=depth + 1,
                field_name=str(key),
            )
            for key, item in value.items()
        }

    fields = getattr(type(value), "model_fields", None)
    if not isinstance(fields, Mapping):
        fields = getattr(value, "__fields__", None)
    if not isinstance(fields, Mapping):
        return value

    updates: dict[str, object] = {}
    for model_field_name in fields:
        try:
            current = getattr(value, model_field_name)
        except (AttributeError, TypeError):
            continue
        branded = _brand_telegram_value(
            current,
            depth=depth + 1,
            field_name=str(model_field_name),
        )
        if branded != current:
            updates[str(model_field_name)] = branded
    return _copy_model(value, updates) if updates else value


async def _call_with_auf_branding(
    bot: Bot,
    method: Any,
    request_timeout: int | None = None,
) -> Any:
    branded_method = _brand_telegram_value(method)
    return await _ORIGINAL_BOT_CALL(
        bot,
        branded_method,
        request_timeout=request_timeout,
    )


def install_auf_branding() -> None:
    """Apply Auf branding and privacy redaction as the final Telegram guard."""

    global _INSTALLED
    if _INSTALLED:
        return
    Bot.__call__ = _call_with_auf_branding  # type: ignore[method-assign]
    _INSTALLED = True


__all__ = (
    "_brand_auf_text",
    "_brand_telegram_value",
    "_brand_velvet_currency_text",
    "_redact_public_technical_text",
    "install_auf_branding",
)
