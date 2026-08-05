from __future__ import annotations

import re

from velvet_bot.app.auf_branding import (
    _brand_auf_text,
    _brand_velvet_currency_text,
    _redact_public_technical_text,
)

_PRIVATE_LINE_PATTERNS = (
    r"(?mi)^Ожидаемая стоимость:.*(?:\n|$)",
    r"(?mi)^Ожидаемое списание:.*(?:\n|$)",
    r"(?mi)^Расчётная себестоимость.*(?:\n|$)",
    r"(?mi)^Стоимость остатка:.*(?:\n|$)",
    r"(?mi)^Себестоимость списаний:.*(?:\n|$)",
    r"(?mi)^Расчёт себестоимости:.*(?:\n|$)",
    r"(?mi)^Последние списания Kie.*(?:\n|$)",
    r"(?mi)^Ошибка доставки:.*(?:\n|$)",
    r"(?mi)^NSFW checker Kie:.*(?:\n|$)",
)
_ATTEMPT_LINE_PATTERN = r"(?mi)^(?:Попытка|Повтор):.*(?:\n|$)"


def sanitize_auf_text(text: str, *, preserve_attempts: bool = False) -> str:
    """Return product-facing Auf copy without provider or accounting internals."""

    cleaned = str(text)
    cleaned = re.sub(
        r"(?m)^Контент: <b>Mature</b>(?: · модерация GRS активна)?\n?",
        "",
        cleaned,
    )
    cleaned = cleaned.replace(
        "Задача поставлена в очередь. Worker скачает выбранные Telegram-фото, "
        "временно загрузит их в Kie и только затем вызовет модель.",
        "Задача поставлена в очередь. Референсы будут подготовлены перед генерацией.",
    )
    cleaned = cleaned.replace(
        "Mature-режим включён. Для Seedream бот передаст документированный "
        "<code>nsfw_checker=false</code>. У Nano Banana Pro отдельного API-флага "
        "отключения фильтра нет, поэтому действует политика самого провайдера.",
        "После выбора модели будут показаны доступные варианты качества.",
    )
    cleaned = cleaned.replace("Изменить Kie", "Основные модели")
    cleaned = cleaned.replace("Изменить GRS", "Nano Banana")
    cleaned = cleaned.replace("Kie.ai:", "Основные модели:")
    cleaned = cleaned.replace("GRS AI:", "Nano Banana:")
    cleaned = cleaned.replace(
        "Глобальные пределы Kie и GRS управляются Стэл.",
        "Глобальные пределы управляются Стэл.",
    )

    cleaned = _redact_public_technical_text(cleaned)
    for pattern in _PRIVATE_LINE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)
    if not preserve_attempts:
        cleaned = re.sub(_ATTEMPT_LINE_PATTERN, "", cleaned)

    provider_forms = {
        "через Kie.ai": "через сервис генерации",
        "через GRS AI": "через сервис генерации",
        "в Kie": "на обработку",
        "из Kie": "из сервиса генерации",
        "GRS AI": "сервис генерации",
        "Kie.ai": "сервис генерации",
        "провайдеру": "сервису генерации",
        "провайдером": "сервисом генерации",
        "провайдера": "сервиса генерации",
        "провайдер": "сервис генерации",
    }
    for old, new in provider_forms.items():
        cleaned = cleaned.replace(old, new)

    cleaned = _brand_velvet_currency_text(_brand_auf_text(cleaned))
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


__all__ = ("sanitize_auf_text",)
