from __future__ import annotations

from html import escape
from typing import Any

_INSTALLED = False


def _label(value: str) -> str:
    return {
        "ready": "готово",
        "review": "ручная проверка",
        "critical": "исправление",
        "accepted": "рекомендуется принять",
        "fix_required": "рекомендуется исправить",
        "manual_review": "решает владелец",
    }.get(value, value or "—")


def install_quality_calibration_report_ui() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from velvet_bot.presentation.telegram.routers.quality_operations_controllers import (
        quality_ai,
    )

    original = quality_ai._report_text

    def wrapped(item: Any) -> str:
        text = original(item)
        report = getattr(item, "report", None)
        report = report if isinstance(report, dict) else {}
        raw = report.get("calibration")
        if not isinstance(raw, dict):
            return text

        active = bool(raw.get("active"))
        sample_count = int(raw.get("sample_count") or 0)
        raw_verdict = str(raw.get("raw_verdict") or "")
        calibrated_verdict = str(raw.get("calibrated_verdict") or "")
        recommendation = str(raw.get("recommendation") or "manual_review")
        lines = [
            "",
            "<b>🎛 Калибровка владельца</b>",
            f"Статус: <b>{'активна' if active else 'собирает выборку'}</b> · "
            f"решений <b>{sample_count}</b>",
            f"Исходный вывод: <b>{escape(_label(raw_verdict))}</b>",
            f"После калибровки: <b>{escape(_label(calibrated_verdict))}</b>",
            f"Маршрутизация: <b>{escape(_label(recommendation))}</b>",
        ]
        if active:
            lines.append(
                "Пороги: готово от "
                f"<b>{int(raw.get('ready_min_score') or 0)}</b>, исправление до "
                f"<b>{int(raw.get('fix_max_score') or 0)}</b>, уверенность от "
                f"<b>{int(raw.get('min_confidence') or 0)}%</b>."
            )
        return (text + "\n" + "\n".join(lines))[:4090]

    quality_ai._report_text = wrapped
    _INSTALLED = True


__all__ = ("install_quality_calibration_report_ui",)
