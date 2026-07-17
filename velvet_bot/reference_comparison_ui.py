from __future__ import annotations

from html import escape


def _list_block(title: str, values: object, emoji: str) -> list[str]:
    if not isinstance(values, list) or not values:
        return []
    lines = ["", f"<b>{emoji} {escape(title)}</b>"]
    for value in values[:8]:
        lines.append(f"• {escape(str(value))}")
    return lines


def format_reference_comparison_report(
    *,
    report_id: int,
    character_name: str,
    reference_index: int,
    reference_total: int,
    report: dict[str, object],
) -> str:
    verdict = str(report.get("verdict") or "partial")
    verdict_label = {
        "strong": "высокое визуальное соответствие",
        "partial": "частичное соответствие",
        "weak": "заметные расхождения",
        "insufficient": "недостаточно видимых деталей",
    }.get(verdict, verdict)
    verdict_emoji = {
        "strong": "✅",
        "partial": "⚠️",
        "weak": "🚨",
        "insufficient": "🔎",
    }.get(verdict, "⚠️")
    lines = [
        f"<b>{verdict_emoji} Сравнение с референсом #{report_id}</b>",
        "",
        f"Персонаж: <b>{escape(character_name)}</b>",
        f"Референс: <b>{reference_index}</b> из <b>{reference_total}</b>",
        f"Вердикт: <b>{escape(verdict_label)}</b>",
        f"Общее соответствие: <b>{int(report.get('overall_score') or 0)} / 100</b>",
        f"Уверенность Qwen: <b>{int(report.get('confidence') or 0)}%</b>",
        "",
        f"Лицо: <b>{int(report.get('face_score') or 0)} / 100</b>",
        f"Волосы: <b>{int(report.get('hair_score') or 0)} / 100</b>",
        f"Телосложение: <b>{int(report.get('body_score') or 0)} / 100</b>",
        f"Уникальные признаки: <b>{int(report.get('unique_traits_score') or 0)} / 100</b>",
        "",
        f"<b>Итог:</b> {escape(str(report.get('summary_ru') or '—'))}",
    ]
    lines.extend(_list_block("Совпадения лица", report.get("face_matches"), "✅"))
    lines.extend(_list_block("Расхождения лица", report.get("face_differences"), "⚠️"))
    lines.extend(_list_block("Совпадения волос", report.get("hair_matches"), "✅"))
    lines.extend(_list_block("Расхождения волос", report.get("hair_differences"), "⚠️"))
    lines.extend(_list_block("Совпадения телосложения", report.get("body_matches"), "✅"))
    lines.extend(_list_block("Расхождения телосложения", report.get("body_differences"), "⚠️"))
    lines.extend(_list_block("Совпавшие уникальные признаки", report.get("unique_matches"), "✅"))
    lines.extend(_list_block("Различия уникальных признаков", report.get("unique_differences"), "⚠️"))
    lines.extend(_list_block("Недостаточно видно", report.get("uncertain_areas"), "🔎"))
    visibility = report.get("visibility")
    if isinstance(visibility, dict):
        lines.extend(
            [
                "",
                "<b>Видимость для проверки:</b>",
                (
                    "• лицо: референс "
                    f"<b>{int(visibility.get('reference_face') or 0)}%</b>, "
                    f"результат <b>{int(visibility.get('result_face') or 0)}%</b>"
                ),
                (
                    "• тело: референс "
                    f"<b>{int(visibility.get('reference_body') or 0)}%</b>, "
                    f"результат <b>{int(visibility.get('result_body') or 0)}%</b>"
                ),
            ]
        )
    lines.extend(
        [
            "",
            "Qwen оценивает только визуальное соответствие видимых черт. "
            "Это не установление личности человека.",
        ]
    )
    return "\n".join(lines)[:4090]


__all__ = ("format_reference_comparison_report",)
