from __future__ import annotations

import unicodedata
from dataclasses import dataclass


POST_TYPE_LABELS = {
    "prompt": "Промты",
    "art": "Арты",
    "announcement": "Анонсы",
    "giveaway": "Розыгрыши",
    "collaboration": "Совместные работы",
    "update": "Обновления",
    "service": "Служебные",
    "unknown": "Не определено",
}


@dataclass(frozen=True, slots=True)
class PostClassification:
    post_type: str
    confidence: int
    reason: str


def classify_post(
    text: str,
    hashtags: tuple[tuple[str, str], ...],
    *,
    is_prompt: bool,
    media_type: str,
) -> PostClassification:
    lowered = unicodedata.normalize("NFKC", text).casefold()
    tags = {normalized for _, normalized in hashtags}

    if is_prompt or "промт" in tags or "prompt" in tags:
        return PostClassification("prompt", 98 if is_prompt else 95, "структура промта")

    if tags.intersection({"розыгрыш", "конкурс", "giveaway"}):
        return PostClassification("giveaway", 98, "хэштег розыгрыша")
    if any(marker in lowered for marker in ("условия участия", "победител", "призовой фонд")):
        return PostClassification("giveaway", 86, "текст розыгрыша")

    if tags.intersection({"анонс", "announcement"}):
        return PostClassification("announcement", 98, "хэштег анонса")
    if any(marker in lowered for marker in ("анонс на", "сегодня выходит", "завтра выходит")):
        return PostClassification("announcement", 84, "текст анонса")

    if tags.intersection({"совместка", "коллаб", "collab", "collaboration"}):
        return PostClassification("collaboration", 98, "хэштег совместной работы")
    if any(marker in lowered for marker in ("совместная работа", "в коллаборации", "совместно с")):
        return PostClassification("collaboration", 84, "текст совместной работы")

    if tags.intersection({"обновление", "update", "релиз"}):
        return PostClassification("update", 96, "хэштег обновления")
    if any(marker in lowered for marker in ("обновление канала", "новая функция", "добавили возможность")):
        return PostClassification("update", 82, "текст обновления")

    if tags.intersection({"служебный", "навигация", "правила", "информация"}):
        return PostClassification("service", 94, "служебный хэштег")
    if any(marker in lowered for marker in ("правила канала", "навигация по каналу", "важная информация")):
        return PostClassification("service", 80, "служебный текст")

    if tags.intersection({"арт", "art", "одиночный", "парный", "мужской", "женский", "мж", "мм", "жж", "мжм"}):
        return PostClassification("art", 90, "хэштег визуальной работы")
    if media_type != "text":
        return PostClassification("art", 62, "медиа без признаков другого типа")

    return PostClassification("unknown", 20, "недостаточно признаков")
