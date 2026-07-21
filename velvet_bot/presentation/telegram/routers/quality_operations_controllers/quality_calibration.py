from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.core.config import load_settings
from velvet_bot.database import Database
from velvet_bot.quality_calibration import (
    CalibrationCase,
    CalibrationProfile,
    QualityCalibrationRepository,
)
from velvet_bot.quality_ui import QualityCallback, quality_callback

router = Router(name=__name__)

_OUTCOME_LABELS = {
    "correct_clean": "✅ правильно пропущено",
    "correct_fix": "✅ правильно найден дефект",
    "useful_warning": "⚠️ полезное предупреждение",
    "false_alarm": "🔔 ложная тревога",
    "missed_problem": "🚨 пропущена проблема",
    "uncertain": "🔎 неоднозначное решение",
}
_VERDICT_LABELS = {
    "ready": "готово",
    "review": "ручная проверка",
    "critical": "исправление",
}
_DECISION_LABELS = {
    "accepted": "принято владельцем",
    "fix_required": "отправлено на исправление",
}
_SECTION_LABELS = {
    "errors": "Ошибки Qwen",
    "false_alarm": "Ложные тревоги",
    "missed_problem": "Пропущенные проблемы",
    "useful": "Полезные решения",
    "all": "Вся история",
}


async def _safe_edit(
    message: Message,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    try:
        await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


def _profile_text(profile: CalibrationProfile, *, provider: str, model: str) -> str:
    if profile.active:
        status = "✅ активна"
        note = (
            "Новые отчёты используют пороги, рассчитанные по вашим решениям. "
            "Исходный вердикт Qwen сохраняется в JSON отчёта."
        )
    else:
        status = "🧪 собирает выборку"
        note = (
            f"Для включения нужно минимум 12 решений, включая хотя бы 3 принятых "
            f"и 3 отправленных на исправление. Осталось решений: "
            f"<b>{profile.collecting_count}</b>."
        )

    return "\n".join(
        [
            "<b>🎛 Калибровка Qwen по решениям владельца</b>",
            "",
            f"Провайдер: <code>{escape(provider)}</code>",
            f"Модель: <code>{escape(model)}</code>",
            f"Статус: <b>{status}</b>",
            f"Решений в выборке: <b>{profile.sample_count}</b>",
            f"Принято: <b>{profile.accepted_count}</b> · "
            f"на исправление: <b>{profile.fix_required_count}</b>",
            "",
            f"Полезность решений Qwen: <b>{profile.usefulness_rate}%</b>",
            f"Ложные тревоги: <b>{profile.false_alarm_rate}%</b>",
            f"Пропущенные проблемы: <b>{profile.missed_problem_rate}%</b>",
            "",
            "<b>Текущие пороги</b>",
            f"• готово: от <b>{profile.ready_min_score}/100</b>",
            f"• исправление: до <b>{profile.fix_max_score}/100</b>",
            f"• минимальная уверенность: <b>{profile.min_confidence}%</b>",
            "",
            note,
            "",
            "Калибровка не меняет найденные дефекты и не принимает решение за владельца. "
            "Она только корректирует очередь ручной проверки.",
        ]
    )


def _profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚨 Ошибки Qwen",
                    callback_data=quality_callback("qcalcases", section="errors"),
                ),
                InlineKeyboardButton(
                    text="✅ Полезные",
                    callback_data=quality_callback("qcalcases", section="useful"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔔 Ложные тревоги",
                    callback_data=quality_callback("qcalcases", section="false_alarm"),
                ),
                InlineKeyboardButton(
                    text="🚨 Пропуски",
                    callback_data=quality_callback("qcalcases", section="missed_problem"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📚 Вся история",
                    callback_data=quality_callback("qcalcases", section="all"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=quality_callback("qcal"),
                ),
                InlineKeyboardButton(
                    text="↩️ Qwen",
                    callback_data=quality_callback("ai_menu"),
                ),
            ],
        ]
    )


def _case_line(case: CalibrationCase) -> str:
    marker = _OUTCOME_LABELS.get(case.outcome, case.outcome)
    return (
        f"{marker} · #{case.media_id} · "
        f"{case.quality_score}%/{case.confidence}%"
    )[:60]


async def _show_profile(message: Message, database: Database) -> None:
    settings = load_settings()
    profile = await QualityCalibrationRepository(database).profile(
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
    )
    await _safe_edit(
        message,
        _profile_text(
            profile,
            provider=settings.ai_vision_provider,
            model=settings.ai_vision_model,
        ),
        _profile_keyboard(),
    )


async def _show_cases(
    message: Message,
    database: Database,
    *,
    section: str,
    page: int,
) -> None:
    settings = load_settings()
    result = await QualityCalibrationRepository(database).list_cases(
        section,
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
        page=page,
    )
    lines = [
        f"<b>🎛 {_SECTION_LABELS.get(section, section)}</b>",
        "",
        f"Событий: <b>{result.total_items}</b>",
        f"Страница: <b>{result.page + 1}</b> из <b>{result.total_pages}</b>",
        "",
        "Событие создаётся каждый раз, когда владелец принимает изображение или "
        "возвращает его на исправление.",
    ]
    rows: list[list[InlineKeyboardButton]] = []
    for case in result.items:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_case_line(case),
                    callback_data=quality_callback(
                        "qcalcase",
                        section=section,
                        page=result.page,
                        item_id=case.feedback_id,
                    ),
                )
            ]
        )
    if result.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=quality_callback(
                        "qcalcases",
                        section=section,
                        page=(result.page - 1) % result.total_pages,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{result.page + 1} / {result.total_pages}",
                    callback_data=quality_callback("noop"),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=quality_callback(
                        "qcalcases",
                        section=section,
                        page=(result.page + 1) % result.total_pages,
                    ),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К калибровке",
                callback_data=quality_callback("qcal"),
            )
        ]
    )
    await _safe_edit(
        message,
        "\n".join(lines),
        InlineKeyboardMarkup(inline_keyboard=rows),
    )


def _case_text(case: CalibrationCase) -> str:
    report = case.report or {}
    raw_summary = " ".join(str(report.get("summary_ru") or "—").split())
    calibration = report.get("calibration")
    calibrated = ""
    if isinstance(calibration, dict):
        raw = _VERDICT_LABELS.get(
            str(calibration.get("raw_verdict") or ""),
            str(calibration.get("raw_verdict") or "—"),
        )
        final = _VERDICT_LABELS.get(
            str(calibration.get("calibrated_verdict") or ""),
            str(calibration.get("calibrated_verdict") or "—"),
        )
        calibrated = f"\nИсходный/калиброванный: <b>{escape(raw)} → {escape(final)}</b>"

    return "\n".join(
        [
            f"<b>🎛 Событие калибровки #{case.feedback_id}</b>",
            "",
            f"media: <b>#{case.media_id}</b>",
            f"Файл: <code>{escape(case.file_name)}</code>",
            f"Вывод Qwen: <b>{escape(_VERDICT_LABELS.get(case.predicted_verdict, case.predicted_verdict))}</b>",
            f"Оценка: <b>{case.quality_score}/100</b> · уверенность <b>{case.confidence}%</b>",
            f"Решение владельца: <b>{escape(_DECISION_LABELS.get(case.owner_decision, case.owner_decision))}</b>",
            f"Результат: <b>{escape(_OUTCOME_LABELS.get(case.outcome, case.outcome))}</b>",
            calibrated,
            "",
            f"<b>Итог отчёта:</b> {escape(raw_summary[:1100])}",
            "",
            f"Решение сохранено: <code>{escape(case.decided_at.isoformat())}</code>",
        ]
    )[:4090]


def _case_keyboard(case: CalibrationCase, *, section: str, page: int) -> InlineKeyboardMarkup:
    quality_section = "accepted" if case.owner_decision == "accepted" else "fix"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧠 Открыть исходный отчёт",
                    callback_data=quality_callback(
                        "qcheck",
                        section=quality_section,
                        item_id=case.media_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К событиям",
                    callback_data=quality_callback(
                        "qcalcases",
                        section=section,
                        page=page,
                    ),
                )
            ],
        ]
    )


@router.message(Command("qwen_calibration", "qcalibration"))
async def handle_calibration_command(message: Message, database: Database) -> None:
    settings = load_settings()
    profile = await QualityCalibrationRepository(database).profile(
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
    )
    await message.answer(
        _profile_text(
            profile,
            provider=settings.ai_vision_provider,
            model=settings.ai_vision_model,
        ),
        reply_markup=_profile_keyboard(),
    )


@router.callback_query(QualityCallback.filter(F.action == "qcal"))
async def handle_calibration_open(
    callback: CallbackQuery,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await callback.answer()
    await _show_profile(callback.message, database)


@router.callback_query(QualityCallback.filter(F.action == "qcalcases"))
async def handle_calibration_cases(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await callback.answer()
    await _show_cases(
        callback.message,
        database,
        section=callback_data.section or "errors",
        page=callback_data.page,
    )


@router.callback_query(QualityCallback.filter(F.action == "qcalcase"))
async def handle_calibration_case(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    case = await QualityCalibrationRepository(database).get_case(callback_data.item_id)
    if case is None:
        await callback.answer("Событие больше не найдено.", show_alert=True)
        return
    await callback.answer()
    await _safe_edit(
        callback.message,
        _case_text(case),
        _case_keyboard(
            case,
            section=callback_data.section or "errors",
            page=callback_data.page,
        ),
    )


__all__ = ("router",)
