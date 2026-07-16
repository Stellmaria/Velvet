from __future__ import annotations

WEEKDAY_LABELS = (
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
)


def format_delay(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    safe = max(0, int(seconds))
    if safe < 60:
        return f"{safe} сек."
    minutes = safe // 60
    if minutes < 60:
        return f"{minutes} мин."
    hours, remaining = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} ч. {remaining} мин." if remaining else f"{hours} ч."
    days, remaining_hours = divmod(hours, 24)
    return (
        f"{days} д. {remaining_hours} ч."
        if remaining_hours
        else f"{days} д."
    )


__all__ = ("WEEKDAY_LABELS", "format_delay")
