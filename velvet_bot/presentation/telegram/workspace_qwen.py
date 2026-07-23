from __future__ import annotations

import asyncio
import io
import logging
from html import escape
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
)
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.ai_quality import _CHECK_KEYS, QualityVisionClient
from velvet_bot.archive_catalog import get_archive_page
from velvet_bot.core.config import load_settings
from velvet_bot.database import Database
from velvet_bot.domains.media_rework.manual import request_manual_rework
from velvet_bot.domains.media_rework.repository import MediaReworkRepository
from velvet_bot.domains.workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.qwen_repository import (
    WorkspaceQwenCheck,
    WorkspaceQwenJob,
    WorkspaceQwenRepository,
)
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.local_ai_runtime import get_local_ai_lock
from velvet_bot.palette_composition_analysis import (
    CompositionAnalysisClient,
    PaletteMetrics,
    build_palette_card,
    extract_palette_metrics,
)
from velvet_bot.presentation.telegram.routers import workspace_owner_controls
from velvet_bot.prompt_result_comparison import PromptResultComparisonClient
from velvet_bot.workspace_ui import WorkspaceCallback, workspace_callback


logger = logging.getLogger(__name__)

_ROLE_RANK = {"viewer": 0, "reviewer": 1, "editor": 2, "admin": 3, "owner": 4}
_SECTION_LABELS = {
    "review": "На проверке",
    "accepted": "Приняты",
    "fix": "На доработке",
    "errors": "Ошибки",
    "queue": "В очереди",
}
_VERDICT_EMOJI = {"ready": "✅", "review": "⚠️", "critical": "🚨"}
_CHECK_LABELS = {
    "anatomy": "Анатомия",
    "hands": "Руки",
    "face": "Лицо",
    "hair": "Волосы",
    "skin_texture": "Текстура кожи",
    "lighting": "Освещение",
    "exposure": "Экспозиция",
    "sharpness": "Резкость",
    "background": "Фон",
    "reflections": "Отражения",
    "composition": "Композиция",
    "compression": "Сжатие",
    "text_watermarks": "Текст и watermark",
    "ui_artifacts": "Интерфейс",
}


class WorkspaceQwenCallback(CallbackData, prefix="wq"):
    action: str
    workspace_id: int
    media_id: int = 0
    character_id: int = 0
    offset: int = 0
    page: int = 0
    section: str = ""
    job_id: int = 0


class WorkspaceQwenForm(StatesGroup):
    prompt_text = State()
    prompt_image = State()
    visual_image = State()


def qwen_callback(
    action: str,
    *,
    workspace_id: int,
    media_id: int = 0,
    character_id: int = 0,
    offset: int = 0,
    page: int = 0,
    section: str = "",
    job_id: int = 0,
) -> str:
    return WorkspaceQwenCallback(
        action=action,
        workspace_id=int(workspace_id),
        media_id=int(media_id),
        character_id=int(character_id),
        offset=max(0, int(offset)),
        page=max(0, int(page)),
        section=section,
        job_id=int(job_id),
    ).pack()


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


async def _require_qwen_context(
    *,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
    user_id: int,
    workspace_id: int,
    minimum_role: WorkspaceRole = "reviewer",
) -> tuple[Workspace, WorkspaceMembership]:
    workspace = await workspace_service.set_active_workspace(
        workspace_id=int(workspace_id),
        user_id=int(user_id),
        global_owner=_is_global_owner(user_id),
    )
    if workspace.is_system:
        raise WorkspaceAccessError(
            "Системный Velvet использует отдельную Qwen-панель Стэл."
        )
    membership = await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=int(user_id),
        minimum_role=minimum_role,
        global_owner=_is_global_owner(user_id),
    )
    if not await workspace_product_service.is_module_enabled(
        workspace_id=workspace.id,
        module_key="qwen",
    ):
        raise WorkspaceAccessError("Модуль Qwen выключен или не разрешён Стэл.")
    settings = await workspace_product_service.get_settings(workspace.id)
    if not settings.qwen_enabled:
        raise WorkspaceAccessError("Qwen выключен в настройках пространства.")
    if not load_settings().ai_vision_enabled:
        raise WorkspaceAccessError("Локальный Qwen сейчас выключен в настройках бота.")
    return workspace, membership


def _can_decide(membership: WorkspaceMembership) -> bool:
    return _ROLE_RANK.get(membership.role, -1) >= _ROLE_RANK["editor"]


async def _edit_or_answer(
    callback: CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    try:
        if callback.message.text:
            await callback.message.edit_text(text, reply_markup=keyboard)
        else:
            await callback.message.answer(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


def _menu_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧠 Проверки архива",
                    callback_data=qwen_callback("checks", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="▶️ Проверить архив",
                    callback_data=qwen_callback("audit", workspace_id=workspace_id),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📝 Промт ↔ результат",
                    callback_data=qwen_callback("prompt", workspace_id=workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎨 Палитра и композиция",
                    callback_data=qwen_callback("visual", workspace_id=workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧬 Сравнение с референсом",
                    callback_data=workspace_callback(
                        "module", workspace_id=workspace_id, module_key="references"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📜 История Qwen",
                    callback_data=qwen_callback("history", workspace_id=workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Моё пространство",
                    callback_data=workspace_callback("home", workspace_id=workspace_id),
                )
            ],
        ]
    )


async def render_workspace_qwen_menu(
    callback: CallbackQuery,
    *,
    workspace: Workspace,
    repository: WorkspaceQwenRepository,
) -> None:
    summary = await repository.summary(workspace.id)
    profile = await repository.calibration_profile(
        workspace_id=workspace.id,
        provider=load_settings().ai_vision_provider,
        model=load_settings().ai_vision_model,
    )
    calibration = (
        f"активна, примеров {profile.sample_count}"
        if profile.active
        else f"собирается, ещё {profile.collecting_count}"
    )
    text = (
        f"<b>🤖 Qwen · {escape(workspace.name)}</b>\n\n"
        "Qwen работает только с материалами, референсами и отчётами этого "
        "пространства. Системный Quality Center Velvet сюда не примешивается.\n\n"
        f"Очередь: <b>{summary.pending + summary.processing}</b> · "
        f"на проверке: <b>{summary.unreviewed}</b> · "
        f"ошибок: <b>{summary.errors + summary.skipped}</b>\n"
        f"✅ чисто: <b>{summary.clean}</b> · ⚠️ замечания: <b>{summary.warnings}</b> · "
        f"🚨 критично: <b>{summary.critical}</b>\n"
        f"Калибровка пространства: <b>{escape(calibration)}</b>"
    )
    await _edit_or_answer(callback, text, _menu_keyboard(workspace.id))


def _list_block(title: str, values: object, emoji: str) -> list[str]:
    if not isinstance(values, list) or not values:
        return []
    lines = ["", f"<b>{emoji} {escape(title)}</b>"]
    for value in values[:8]:
        lines.append(f"• {escape(str(value))}")
    return lines


def _check_text(check: WorkspaceQwenCheck) -> str:
    if check.status in {"pending", "processing"}:
        label = "ожидает обработки" if check.status == "pending" else "анализируется"
        return (
            f"<b>🧠 Qwen-проверка media #{check.media_id}</b>\n\n"
            f"Файл: <code>{escape(check.file_name)}</code>\n"
            f"Статус: <b>{label}</b>"
        )
    if check.status in {"error", "skipped"}:
        return (
            f"<b>❌ Qwen-проверка media #{check.media_id}</b>\n\n"
            f"Файл: <code>{escape(check.file_name)}</code>\n"
            f"Статус: <b>{escape(check.status)}</b>\n\n"
            f"<code>{escape(check.error_message or 'Причина не сохранена.')}</code>"
        )
    report = check.report or {}
    verdict = check.verdict or str(report.get("verdict") or "review")
    label = {
        "ready": "готово к публикации",
        "review": "нужна ручная проверка",
        "critical": "рекомендуется исправление",
    }.get(verdict, verdict)
    decision = {
        None: "не принято",
        "accepted": "✅ принято",
        "fix_required": "🛠 отправлено на доработку",
    }.get(check.decision, check.decision or "не принято")
    lines = [
        f"<b>{_VERDICT_EMOJI.get(verdict, '⚠️')} Qwen-проверка media #{check.media_id}</b>",
        "",
        f"Файл: <code>{escape(check.file_name)}</code>",
        f"Вердикт: <b>{escape(label)}</b>",
        f"Качество: <b>{check.quality_score if check.quality_score is not None else '—'} / 100</b>",
        f"Уверенность: <b>{check.confidence if check.confidence is not None else '—'}%</b>",
        f"Решение: <b>{escape(decision)}</b>",
        "",
        f"<b>Итог:</b> {escape(str(report.get('summary_ru') or '—'))}",
    ]
    lines.extend(_list_block("Критичные проблемы", report.get("critical_issues"), "🚨"))
    lines.extend(_list_block("Замечания", report.get("warnings"), "⚠️"))
    lines.extend(_list_block("Сильные стороны", report.get("strengths"), "✅"))
    checks = report.get("checks")
    if isinstance(checks, dict):
        weakest = sorted(
            (
                (key, int(checks.get(key) or 0))
                for key in _CHECK_KEYS
                if isinstance(checks.get(key), int)
            ),
            key=lambda pair: pair[1],
        )[:7]
        if weakest:
            lines.extend(["", "<b>Слабые области:</b>"])
            for key, value in weakest:
                lines.append(f"• {escape(_CHECK_LABELS.get(key, key))}: <b>{value}/100</b>")
    return "\n".join(lines)[:4090]


def _check_keyboard(
    check: WorkspaceQwenCheck,
    *,
    can_decide: bool,
    page: int = 0,
    section: str = "review",
    character_id: int = 0,
    offset: int = 0,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if check.status == "ready" and can_decide:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Принять",
                    callback_data=qwen_callback(
                        "accept",
                        workspace_id=check.workspace_id,
                        media_id=check.media_id,
                        page=page,
                        section=section,
                    ),
                ),
                InlineKeyboardButton(
                    text="🛠 На доработку",
                    callback_data=qwen_callback(
                        "fix",
                        workspace_id=check.workspace_id,
                        media_id=check.media_id,
                        page=page,
                        section=section,
                    ),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔄 Проверить заново",
                callback_data=qwen_callback(
                    "retry",
                    workspace_id=check.workspace_id,
                    media_id=check.media_id,
                    page=page,
                    section=section,
                ),
            )
        ]
    )
    if character_id:
        rows.append(
            [
                InlineKeyboardButton(
                    text="↩️ К материалу",
                    callback_data=workspace_owner_controls._archive_callback(
                        "show",
                        workspace_id=check.workspace_id,
                        character_id=character_id,
                        offset=offset,
                        media_id=check.media_id,
                    ),
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="↩️ К списку",
                    callback_data=qwen_callback(
                        "checks",
                        workspace_id=check.workspace_id,
                        page=page,
                        section=section,
                    ),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _checks_keyboard(workspace_id: int, section: str, page) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=("• " if section == "review" else "") + "🧠 Проверить",
                callback_data=qwen_callback(
                    "checks", workspace_id=workspace_id, section="review"
                ),
            ),
            InlineKeyboardButton(
                text=("• " if section == "queue" else "") + "⏳ Очередь",
                callback_data=qwen_callback(
                    "checks", workspace_id=workspace_id, section="queue"
                ),
            ),
        ],
        [
            InlineKeyboardButton(
                text=("• " if section == "accepted" else "") + "✅ Приняты",
                callback_data=qwen_callback(
                    "checks", workspace_id=workspace_id, section="accepted"
                ),
            ),
            InlineKeyboardButton(
                text=("• " if section == "fix" else "") + "🛠 Доработка",
                callback_data=qwen_callback(
                    "checks", workspace_id=workspace_id, section="fix"
                ),
            ),
        ],
        [
            InlineKeyboardButton(
                text=("• " if section == "errors" else "") + "❌ Ошибки",
                callback_data=qwen_callback(
                    "checks", workspace_id=workspace_id, section="errors"
                ),
            )
        ],
    ]
    for item in page.items:
        score = f"{item.quality_score}%" if item.quality_score is not None else item.status
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{_VERDICT_EMOJI.get(item.verdict or '', '🧠')} {score} · #{item.media_id} · {item.file_name}"[:60],
                    callback_data=qwen_callback(
                        "check",
                        workspace_id=workspace_id,
                        media_id=item.media_id,
                        page=page.page,
                        section=section,
                    ),
                )
            ]
        )
    if page.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=qwen_callback(
                        "checks",
                        workspace_id=workspace_id,
                        page=(page.page - 1) % page.total_pages,
                        section=section,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{page.page + 1} / {page.total_pages}",
                    callback_data=qwen_callback("noop", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=qwen_callback(
                        "checks",
                        workspace_id=workspace_id,
                        page=(page.page + 1) % page.total_pages,
                        section=section,
                    ),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Qwen",
                callback_data=qwen_callback("menu", workspace_id=workspace_id),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _download_image(bot: Bot, file_id: str) -> bytes:
    errors: list[BaseException] = []
    for attempt in range(1, 4):
        try:
            target = io.BytesIO()
            await bot.download(file_id, destination=target, timeout=90, seek=True)
            data = target.getvalue()
            if data:
                return data
            errors.append(RuntimeError("Telegram вернул пустой файл."))
        except asyncio.CancelledError:
            raise
        except TelegramBadRequest as error:
            errors.append(error)
            break
        except (TelegramNetworkError, TimeoutError, ConnectionError, OSError) as error:
            errors.append(error)
            if attempt < 3:
                await asyncio.sleep((1.0, 3.0)[attempt - 1])
        except TelegramAPIError as error:
            errors.append(error)
            break
    raise RuntimeError(f"Не удалось скачать изображение: {errors[-1] if errors else 'нет данных'}")


def _message_image(message: Message) -> tuple[str, str | None] | None:
    if message.photo:
        photo = message.photo[-1]
        return photo.file_id, photo.file_unique_id
    if message.document and (message.document.mime_type or "").startswith("image/"):
        return message.document.file_id, message.document.file_unique_id
    return None


def _prompt_report_text(job_id: int, report: dict[str, Any]) -> str:
    verdict = str(report.get("verdict") or "partial")
    labels = {
        "strong": "сильное соответствие",
        "partial": "частичное соответствие",
        "weak": "слабое соответствие",
        "insufficient": "недостаточно данных",
    }
    lines = [
        "<b>📝 Qwen · промт против результата</b>",
        "",
        f"Задание: <b>#{job_id}</b>",
        f"Вердикт: <b>{escape(labels.get(verdict, verdict))}</b>",
        f"Соответствие: <b>{int(report.get('overall_score') or 0)} / 100</b>",
        f"Уверенность: <b>{int(report.get('confidence') or 0)}%</b>",
        "",
        f"Персонажи: <b>{int(report.get('subject_score') or 0)}</b> · "
        f"композиция: <b>{int(report.get('composition_score') or 0)}</b>",
        f"Свет: <b>{int(report.get('lighting_score') or 0)}</b> · "
        f"палитра: <b>{int(report.get('palette_score') or 0)}</b>",
        "",
        f"<b>Итог:</b> {escape(str(report.get('summary_ru') or '—'))}",
    ]
    lines.extend(_list_block("Выполнено", report.get("matched_requirements"), "✅"))
    lines.extend(_list_block("Нарушено", report.get("violated_requirements"), "❌"))
    lines.extend(_list_block("Нельзя проверить", report.get("uncertain_requirements"), "🔎"))
    lines.extend(_list_block("Что исправить сначала", report.get("priorities"), "🛠"))
    return "\n".join(lines)[:4090]


def _visual_report_text(job_id: int, metrics: PaletteMetrics, report: dict[str, Any]) -> str:
    colors = " · ".join(
        f"<code>{color.hex_code}</code> {color.share:.1f}%" for color in metrics.colors
    ) or "—"
    lines = [
        "<b>🎨 Qwen · палитра и композиция</b>",
        "",
        f"Задание: <b>#{job_id}</b>",
        f"Размер: <b>{metrics.width} × {metrics.height}</b>",
        f"Композиция: <b>{int(report.get('composition_score') or 0)} / 100</b> · "
        f"уверенность <b>{int(report.get('confidence') or 0)}%</b>",
        f"Баланс: <b>{int(report.get('balance_score') or 0)}</b> · "
        f"кадрирование: <b>{int(report.get('framing_score') or 0)}</b>",
        f"Свет: <b>{int(report.get('lighting_score') or 0)}</b> · "
        f"палитра: <b>{int(report.get('palette_harmony_score') or 0)}</b>",
        f"Цвета: {colors}",
        "",
        f"<b>Итог:</b> {escape(str(report.get('summary_ru') or '—'))}",
        f"<b>Фокус:</b> {escape(str(report.get('focal_point_ru') or '—'))}",
        f"<b>Обрезание:</b> {escape(str(report.get('crop_assessment_ru') or '—'))}",
    ]
    lines.extend(_list_block("Сильные стороны", report.get("strengths"), "✅"))
    lines.extend(_list_block("Проблемы", report.get("issues"), "⚠️"))
    lines.extend(_list_block("Исправления", report.get("recommendations"), "🛠"))
    return "\n".join(lines)[:4090]


def _job_label(job: WorkspaceQwenJob) -> str:
    return {
        "quality_image": "Проверка качества",
        "prompt_result": "Промт ↔ результат",
        "palette_composition": "Палитра и композиция",
        "reference_comparison": "Сравнение с референсом",
        "archive_audit": "Проверка архива",
    }.get(job.kind, job.title)


def _history_keyboard(workspace_id: int, page) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for job in page.items:
        icon = {"ready": "✅", "error": "❌", "processing": "⏳", "pending": "🕒"}.get(
            job.status, "🤖"
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{icon} #{job.id} · {_job_label(job)}"[:60],
                    callback_data=qwen_callback(
                        "job",
                        workspace_id=workspace_id,
                        job_id=job.id,
                        page=page.page,
                    ),
                )
            ]
        )
    if page.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=qwen_callback(
                        "history",
                        workspace_id=workspace_id,
                        page=(page.page - 1) % page.total_pages,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{page.page + 1} / {page.total_pages}",
                    callback_data=qwen_callback("noop", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=qwen_callback(
                        "history",
                        workspace_id=workspace_id,
                        page=(page.page + 1) % page.total_pages,
                    ),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Qwen",
                callback_data=qwen_callback("menu", workspace_id=workspace_id),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def handle_workspace_qwen_module(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
    database: Database,
) -> None:
    try:
        workspace, _ = await _require_qwen_context(
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
            user_id=callback.from_user.id,
            workspace_id=callback_data.workspace_id,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await render_workspace_qwen_menu(
        callback,
        workspace=workspace,
        repository=WorkspaceQwenRepository(database),
    )


async def handle_workspace_qwen_archive_action(
    callback: CallbackQuery,
    callback_data: workspace_owner_controls.WorkspacePersonalArchiveCallback,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
    database: Database,
) -> None:
    try:
        workspace, membership = await _require_qwen_context(
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
            user_id=callback.from_user.id,
            workspace_id=callback_data.workspace_id,
        )
        if not await workspace_product_service.is_module_enabled(
            workspace_id=workspace.id,
            module_key="archive",
        ):
            raise WorkspaceAccessError("Модуль архива выключен.")
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    page = await get_archive_page(
        database,
        callback_data.character_id,
        callback_data.offset,
        workspace_id=workspace.id,
        include_adult_restricted=True,
        include_oversized_images=True,
    )
    if page is None or page.media is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return
    if callback_data.media_id and callback_data.media_id != page.media.id:
        await callback.answer("Архив изменился. Откройте материал заново.", show_alert=True)
        return
    if page.media.media_type != "photo" and not page.media.is_image_document:
        await callback.answer("Qwen проверяет изображения, а не видео и анимации.", show_alert=True)
        return
    repository = WorkspaceQwenRepository(database)
    await repository.enqueue_media(
        workspace_id=workspace.id,
        media_id=page.media.id,
    )
    check = await repository.get_check(
        workspace_id=workspace.id,
        media_id=page.media.id,
    )
    if check is None or not isinstance(callback.message, Message):
        await callback.answer("Не удалось создать Qwen-проверку.", show_alert=True)
        return
    await callback.message.answer(
        _check_text(check),
        reply_markup=_check_keyboard(
            check,
            can_decide=_can_decide(membership),
            character_id=page.character.id,
            offset=page.offset,
        ),
    )
    await callback.answer("Qwen-проверка открыта.")


async def handle_workspace_qwen_callback(
    callback: CallbackQuery,
    callback_data: WorkspaceQwenCallback,
    state: FSMContext,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
    database: Database,
) -> None:
    if callback_data.action == "noop":
        await callback.answer()
        return
    try:
        workspace, membership = await _require_qwen_context(
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
            user_id=callback.from_user.id,
            workspace_id=callback_data.workspace_id,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    repository = WorkspaceQwenRepository(database)
    action = callback_data.action

    if action == "menu":
        await state.clear()
        await render_workspace_qwen_menu(callback, workspace=workspace, repository=repository)
        return
    if action == "audit":
        queued = await repository.enqueue_archive(workspace_id=workspace.id)
        job_id = await repository.create_job(
            workspace_id=workspace.id,
            kind="archive_audit",
            title="Проверка архива",
            provider=load_settings().ai_vision_provider,
            model=load_settings().ai_vision_model,
            created_by=callback.from_user.id,
            request_payload={"queued": queued},
        )
        text = (
            f"В очередь добавлено новых изображений: {queued}."
            if queued
            else "Все изображения архива уже имеют проверку или стоят в очереди."
        )
        await repository.finish_job(
            job_id=job_id,
            result_text=text,
            result_payload={"queued": queued},
        )
        await callback.answer(text, show_alert=True)
        return
    if action == "checks":
        section = callback_data.section or "review"
        page = await repository.list_checks(
            workspace_id=workspace.id,
            section=section,
            page=callback_data.page,
        )
        text = (
            f"<b>🧠 Qwen · {escape(_SECTION_LABELS.get(section, section))}</b>\n\n"
            f"Найдено: <b>{page.total_items}</b>"
        )
        await _edit_or_answer(
            callback,
            text,
            _checks_keyboard(workspace.id, section, page),
        )
        return
    if action == "check":
        check = await repository.get_check(
            workspace_id=workspace.id,
            media_id=callback_data.media_id,
        )
        if check is None:
            await callback.answer("Проверка больше недоступна.", show_alert=True)
            return
        await _edit_or_answer(
            callback,
            _check_text(check),
            _check_keyboard(
                check,
                can_decide=_can_decide(membership),
                page=callback_data.page,
                section=callback_data.section or "review",
            ),
        )
        return
    if action == "retry":
        await repository.retry(
            workspace_id=workspace.id,
            media_id=callback_data.media_id,
        )
        check = await repository.get_check(
            workspace_id=workspace.id,
            media_id=callback_data.media_id,
        )
        if check is None:
            await callback.answer("Материал больше недоступен.", show_alert=True)
            return
        await _edit_or_answer(
            callback,
            _check_text(check),
            _check_keyboard(
                check,
                can_decide=_can_decide(membership),
                page=callback_data.page,
                section=callback_data.section or "review",
            ),
        )
        return
    if action in {"accept", "fix"}:
        if not _can_decide(membership):
            await callback.answer(
                "Решение может принять редактор, администратор или владелец.",
                show_alert=True,
            )
            return
        check = await repository.get_check(
            workspace_id=workspace.id,
            media_id=callback_data.media_id,
        )
        if check is None or check.status != "ready":
            await callback.answer("Готовый отчёт больше недоступен.", show_alert=True)
            return
        decision = "accepted" if action == "accept" else "fix_required"
        changed = await repository.set_decision(
            workspace_id=workspace.id,
            media_id=check.media_id,
            decision=decision,
            user_id=callback.from_user.id,
        )
        rework = MediaReworkRepository(database, workspace_id=workspace.id)
        if action == "fix":
            await request_manual_rework(
                database,
                media_id=check.media_id,
                user_id=callback.from_user.id,
                workspace_id=workspace.id,
                reason=str((check.report or {}).get("summary_ru") or "Qwen рекомендовал доработку."),
            )
        elif await rework.is_active(check.media_id):
            await rework.accept(check.media_id, callback.from_user.id)
        refreshed = await repository.get_check(
            workspace_id=workspace.id,
            media_id=check.media_id,
        )
        if refreshed is None:
            await callback.answer("Проверка больше недоступна.", show_alert=True)
            return
        await _edit_or_answer(
            callback,
            _check_text(refreshed),
            _check_keyboard(
                refreshed,
                can_decide=True,
                page=callback_data.page,
                section=callback_data.section or "review",
            ),
        )
        if not changed:
            await callback.answer("Решение уже было сохранено.", show_alert=True)
        return
    if action == "prompt":
        await state.set_state(WorkspaceQwenForm.prompt_text)
        await state.update_data(workspace_id=workspace.id)
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "<b>📝 Промт против результата · шаг 1 из 2</b>\n\n"
                "Отправьте полное исходное техническое задание одним сообщением."
            )
        await callback.answer()
        return
    if action == "visual":
        await state.set_state(WorkspaceQwenForm.visual_image)
        await state.update_data(workspace_id=workspace.id)
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "<b>🎨 Палитра и композиция</b>\n\n"
                "Отправьте изображение как фото или image-файл."
            )
        await callback.answer()
        return
    if action == "history":
        page = await repository.list_jobs(
            workspace_id=workspace.id,
            page=callback_data.page,
        )
        await _edit_or_answer(
            callback,
            f"<b>📜 История Qwen</b>\n\nЗаданий: <b>{page.total_items}</b>",
            _history_keyboard(workspace.id, page),
        )
        return
    if action == "job":
        job = await repository.get_job(
            workspace_id=workspace.id,
            job_id=callback_data.job_id,
        )
        if job is None:
            await callback.answer("Задание больше недоступно.", show_alert=True)
            return
        text = job.result_text or (
            f"<b>{escape(_job_label(job))}</b>\n\n"
            f"Статус: <b>{escape(job.status)}</b>\n"
            f"Этап: <b>{escape(job.stage)}</b>\n"
            f"Ошибка: <code>{escape(job.error_message or '—')}</code>"
        )
        await _edit_or_answer(
            callback,
            text[:4090],
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="↩️ К истории",
                            callback_data=qwen_callback(
                                "history",
                                workspace_id=workspace.id,
                                page=callback_data.page,
                            ),
                        )
                    ]
                ]
            ),
        )
        return
    await callback.answer("Неизвестное действие Qwen.", show_alert=True)


async def _require_form_context(
    message: Message,
    state: FSMContext,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> tuple[Workspace, WorkspaceMembership, dict[str, Any]] | None:
    if message.from_user is None:
        return None
    data = await state.get_data()
    workspace_id = int(data.get("workspace_id") or 0)
    try:
        workspace, membership = await _require_qwen_context(
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
            user_id=message.from_user.id,
            workspace_id=workspace_id,
        )
    except WorkspaceAccessError as error:
        await state.clear()
        await message.answer(f"❌ {escape(str(error))}")
        return None
    return workspace, membership, data


async def handle_workspace_qwen_prompt_text(
    message: Message,
    state: FSMContext,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    context = await _require_form_context(
        message, state, workspace_service, workspace_product_service
    )
    if context is None:
        return
    prompt = " ".join((message.text or "").split()).strip()
    if len(prompt) < 20:
        await message.answer("Промт слишком короткий. Отправьте полное техническое задание.")
        return
    await state.update_data(prompt_text=prompt[:12000])
    await state.set_state(WorkspaceQwenForm.prompt_image)
    await message.answer(
        "<b>🖼 Шаг 2 из 2</b>\n\nОтправьте готовое изображение как фото или image-файл."
    )


async def handle_workspace_qwen_prompt_image(
    message: Message,
    state: FSMContext,
    database: Database,
    bot: Bot,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    context = await _require_form_context(
        message, state, workspace_service, workspace_product_service
    )
    if context is None:
        return
    workspace, _, data = context
    image_file = _message_image(message)
    if image_file is None:
        await message.answer("Нужно отправить фотографию или image-документ.")
        return
    prompt = str(data.get("prompt_text") or "")
    settings = load_settings()
    repository = WorkspaceQwenRepository(database)
    file_id, unique_id = image_file
    job_id = await repository.create_job(
        workspace_id=workspace.id,
        kind="prompt_result",
        title="Промт против результата",
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
        created_by=message.from_user.id if message.from_user else None,
        request_payload={
            "result_file_id": file_id,
            "result_file_unique_id": unique_id,
            "prompt_length": len(prompt),
        },
    )
    status = await message.answer(f"<b>📝 Qwen-задание #{job_id}</b>\n\nСкачиваю изображение…")
    try:
        await repository.set_job_stage(job_id, "downloading")
        image = await _download_image(bot, file_id)
        await repository.set_job_stage(job_id, "analyzing")
        client = PromptResultComparisonClient(
            provider=settings.ai_vision_provider,
            base_url=settings.ai_vision_base_url,
            model=settings.ai_vision_model,
            api_key=settings.ai_vision_api_key,
            timeout_seconds=settings.ai_vision_timeout_seconds,
        )
        async with get_local_ai_lock():
            report = await client.compare(prompt, image)
        rendered = _prompt_report_text(job_id, report)
        await repository.finish_job(
            job_id=job_id,
            result_text=rendered,
            result_payload=report,
        )
        await status.edit_text(
            rendered,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="↩️ Qwen",
                            callback_data=qwen_callback("menu", workspace_id=workspace.id),
                        )
                    ]
                ]
            ),
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:  # p2-approved-boundary: workspace-qwen-prompt-result
        logger.exception("Workspace prompt comparison failed workspace_id=%s", workspace.id)
        await repository.fail_job(job_id=job_id, error=error)
        await status.edit_text(f"❌ Qwen не завершил сравнение.\n\n<code>{escape(str(error))[:1200]}</code>")
    finally:
        await state.clear()


async def handle_workspace_qwen_visual_image(
    message: Message,
    state: FSMContext,
    database: Database,
    bot: Bot,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    context = await _require_form_context(
        message, state, workspace_service, workspace_product_service
    )
    if context is None:
        return
    workspace, _, _ = context
    image_file = _message_image(message)
    if image_file is None:
        await message.answer("Нужно отправить фотографию или image-документ.")
        return
    file_id, unique_id = image_file
    settings = load_settings()
    repository = WorkspaceQwenRepository(database)
    job_id = await repository.create_job(
        workspace_id=workspace.id,
        kind="palette_composition",
        title="Палитра и композиция",
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
        created_by=message.from_user.id if message.from_user else None,
        request_payload={
            "result_file_id": file_id,
            "result_file_unique_id": unique_id,
        },
    )
    status = await message.answer(f"<b>🎨 Qwen-задание #{job_id}</b>\n\nИзмеряю палитру…")
    try:
        await repository.set_job_stage(job_id, "downloading")
        image = await _download_image(bot, file_id)
        await repository.set_job_stage(job_id, "preparing")
        metrics = await asyncio.to_thread(extract_palette_metrics, image)
        client = CompositionAnalysisClient(
            provider=settings.ai_vision_provider,
            base_url=settings.ai_vision_base_url,
            model=settings.ai_vision_model,
            api_key=settings.ai_vision_api_key,
            timeout_seconds=settings.ai_vision_timeout_seconds,
        )
        await repository.set_job_stage(job_id, "analyzing")
        async with get_local_ai_lock():
            report = await client.analyze_composition(image, metrics)
        rendered = _visual_report_text(job_id, metrics, report)
        payload = dict(report)
        payload["palette_metrics"] = metrics.as_dict()
        await repository.finish_job(
            job_id=job_id,
            result_text=rendered,
            result_payload=payload,
        )
        card = await asyncio.to_thread(build_palette_card, metrics)
        await message.answer_document(
            BufferedInputFile(card, filename=f"qwen-palette-{job_id}.png"),
            caption="Палитра из Qwen-анализа личного пространства",
        )
        await status.edit_text(
            rendered,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="↩️ Qwen",
                            callback_data=qwen_callback("menu", workspace_id=workspace.id),
                        )
                    ]
                ]
            ),
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:  # p2-approved-boundary: workspace-qwen-visual
        logger.exception("Workspace visual analysis failed workspace_id=%s", workspace.id)
        await repository.fail_job(job_id=job_id, error=error)
        await status.edit_text(f"❌ Qwen не завершил анализ.\n\n<code>{escape(str(error))[:1200]}</code>")
    finally:
        await state.clear()


def register_workspace_qwen(router: Router) -> None:
    router.callback_query.register(
        handle_workspace_qwen_module,
        WorkspaceCallback.filter((F.action == "module") & (F.module_key == "qwen")),
    )
    router.callback_query.register(
        handle_workspace_qwen_archive_action,
        workspace_owner_controls.WorkspacePersonalArchiveCallback.filter(
            F.action == "qwen"
        ),
    )
    router.callback_query.register(
        handle_workspace_qwen_callback,
        WorkspaceQwenCallback.filter(),
    )
    router.message.register(
        handle_workspace_qwen_prompt_text,
        WorkspaceQwenForm.prompt_text,
        F.text,
    )
    router.message.register(
        handle_workspace_qwen_prompt_image,
        WorkspaceQwenForm.prompt_image,
        F.photo | F.document,
    )
    router.message.register(
        handle_workspace_qwen_visual_image,
        WorkspaceQwenForm.visual_image,
        F.photo | F.document,
    )


__all__ = (
    "WorkspaceQwenCallback",
    "WorkspaceQwenForm",
    "qwen_callback",
    "register_workspace_qwen",
    "render_workspace_qwen_menu",
)
