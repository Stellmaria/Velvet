from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected block not found in {path}: {old[:80]!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def regex_replace(path: str, pattern: str, replacement: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"Expected one regex match in {path}, got {count}")
    target.write_text(updated, encoding="utf-8")


def patch_velvet_ai() -> None:
    path = "velvet_bot/presentation/telegram/routers/quality_operations_controllers/velvet_ai.py"
    replace(
        path,
        "from velvet_bot.ai_job_runtime import AIJobTracker\n",
        "from velvet_bot.ai_job_runtime import AIJobTracker\n"
        "from velvet_bot.ai_quality import AIQualityRepository\n",
    )
    replace(
        path,
        "from velvet_bot.database import Database\n",
        "from velvet_bot.database import Database\n"
        "from velvet_bot.domains.media_rework import MediaReworkRepository\n",
    )
    replace(path, 'text="↩️ Velvet AI"', 'text="↩️ Qwen"')
    old = '''@router.callback_query(QualityCallback.filter(F.action == "ai_menu"))
async def handle_velvet_ai_menu(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    settings = load_settings()
    text, keyboard = build_velvet_ai_menu(
        enabled=settings.ai_vision_enabled,
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
    )
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise
    await callback.answer()
'''
    new = '''@router.callback_query(QualityCallback.filter(F.action == "ai_menu"))
async def handle_velvet_ai_menu(
    callback: CallbackQuery,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    settings = load_settings()
    quality, rework = await asyncio.gather(
        AIQualityRepository(database).summary(),
        MediaReworkRepository(database).summary(),
    )
    text, keyboard = build_velvet_ai_menu(
        enabled=settings.ai_vision_enabled,
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
        quality=quality,
        rework=rework,
    )
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise
    await callback.answer()
'''
    replace(path, old, new)
    replace(
        path,
        "Запустите проверку заново из Velvet AI.",
        "Запустите проверку заново из панели Qwen.",
    )


def patch_quality_operations() -> None:
    path = "velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_operations.py"
    pattern = r"def build_quality_operations_menu\(.*?\n    return text, keyboard\n"
    replacement = '''def build_quality_operations_menu(
    summary: AIQualitySummary,
    worker: WorkerSnapshot | None,
) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "<b>🖼 Qwen · проверка архива</b>\n\n"
        "Ручная проверка изображения и управление фоновым worker.\n\n"
        f"Очередь: <b>{summary.pending + summary.processing}</b> · "
        f"готово <b>{summary.ready}</b>\n"
        f"Без решения: <b>{summary.unreviewed}</b> · "
        f"ошибок <b>{summary.errors + summary.skipped}</b>\n"
        f"Worker: <code>{escape(_worker_text(worker))}</code>"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖼 Новое фото",
                    callback_data=quality_callback("quality_upload"),
                ),
                InlineKeyboardButton(
                    text="📋 Отчёты",
                    callback_data=quality_callback("qchecks", section="review"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Ошибки",
                    callback_data=quality_callback("qchecks", section="errors"),
                ),
                InlineKeyboardButton(
                    text="🛠 Доработка",
                    callback_data=quality_callback("reworks"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🕘 Последние",
                    callback_data=quality_callback("quality_recent"),
                ),
                InlineKeyboardButton(
                    text="▶️ Запуск",
                    callback_data=quality_callback("quality_run"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔁 Повтор ошибок",
                    callback_data=quality_callback("quality_retry_errors"),
                ),
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=quality_callback("quality_ops"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Qwen",
                    callback_data=quality_callback("ai_menu"),
                )
            ],
        ]
    )
    return text, keyboard
'''
    regex_replace(path, pattern, replacement)


def patch_rework_ui() -> None:
    path = "velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_rework.py"
    replace(
        path,
        '''_SOURCE_LABELS = {
    "qwen": "Qwen",
    "admin": "администратор",
    "mixed": "Qwen + администратор",
}
''',
        '''_SOURCE_LABELS = {
    "qwen": "Qwen",
    "admin": "Стэл",
    "mixed": "Стэл + Qwen",
}
''',
    )
    replace(path, '[:60],', '[:46],')
    replace(path, 'text="🔄 Обновить"', 'text="🔄"')
    replace(path, 'text="↩️ К аудиту"', 'text="↩️ Qwen"')
    replace(path, 'callback_data=quality_callback("menu"),', 'callback_data=quality_callback("ai_menu"),')
    replace(
        path,
        'f"Страница: <b>{page.page + 1}</b> из <b>{page.total_pages}</b>",\n            "",\n            "В очередь попадают критичные оценки Qwen и ручные решения администратора.",',
        'f"Стэл: <b>{summary.stel_priority}</b> · Qwen: <b>{summary.qwen_only}</b>",\n            f"Страница: <b>{page.page + 1}</b> из <b>{page.total_pages}</b>",\n            "",\n            "Работы Стэл показаны первыми. Активная доработка временно скрыта из публичного архива.",',
    )
    replace(path, 'text="🔄 Вернуть на проверку Qwen"', 'text="🔄 Qwen-проверка"')
    replace(path, 'text="↩️ К очереди"', 'text="↩️ Очередь"')
    replace(path, 'message = "Работа принята."', 'message = "Работа принята. Публичная видимость восстановлена."')
    replace(path, 'message = "Работа снята с доработки."', 'message = "Работа снята. Публичная видимость восстановлена."')


def patch_owner_menu() -> None:
    path = "velvet_bot/owner_menu.py"
    replacements = {
        'text="💧 Водяной знак"': 'text="💧 Знак"',
        'text="🧰 Все действия"': 'text="🧰 Действия"',
        'text="🛡 Supervisor и Codex"': 'text="🛡 Supervisor"',
        'text="🤖 Velvet AI"': 'text="🤖 Qwen"',
        'text="💾 Резервные копии"': 'text="💾 Backup"',
        'text="ℹ️ Как пользоваться"': 'text="ℹ️ Справка"',
        'text="↩️ Центр управления"': 'text="🏠 Главная"',
        '🤖 <b>Velvet AI</b> — качество, референсы, промт против результата, ': '🤖 <b>Qwen</b> — архивная проверка, доработка, референсы, промт против результата, ',
    }
    for old, new in replacements.items():
        replace(path, old, new)


def patch_quality_dashboard() -> None:
    path = "velvet_bot/quality_ui.py"
    old = '''    if ai_quality is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🧠 Проверка изображений · {ai_quality.unreviewed}",
                    callback_data=quality_callback("qchecks", section="review"),
                ),
                InlineKeyboardButton(
                    text="🔄 Ошибки Qwen",
                    callback_data=quality_callback("quality_retry_errors"),
                ),
            ]
        )
'''
    new = '''    if ai_quality is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🤖 Qwen · {ai_quality.pending + ai_quality.processing}",
                    callback_data=quality_callback("ai_menu"),
                )
            ]
        )
'''
    replace(path, old, new)
    replacements = {
        'text="🎞 Предложения медиасетов"': 'text="🎞 Медиасеты"',
        'text=f"👥 Без категории · {summary.missing_category}"': 'text=f"👥 Категория · {summary.missing_category}"',
        'text=f"🌌 Без вселенной · {summary.missing_universe}"': 'text=f"🌌 Вселенная · {summary.missing_universe}"',
        'text=f"📖 Без истории · {summary.missing_story}"': 'text=f"📖 История · {summary.missing_story}"',
        'text=f"📦 Без материалов · {summary.empty_characters}"': 'text=f"📦 Пустые · {summary.empty_characters}"',
        'text=f"📝 Без поста · {summary.media_without_prompt}"': 'text=f"📝 Без поста · {summary.media_without_prompt}"',
        'text=f"⚠ Ошибки сканирования · {summary.scan_errors}"': 'text=f"⚠ Скан · {summary.scan_errors}"',
        'text=f"#️⃣ Не распознано · {summary.unresolved_hashtags}"': 'text=f"#️⃣ Хэштеги · {summary.unresolved_hashtags}"',
        'text=f"🗃 Сиротские записи · {summary.orphan_media}"': 'text=f"🗃 Сироты · {summary.orphan_media}"',
        'text="↩️ К аудиту"': 'text="↩️ Аудит"',
        'text="♻️ Сбросить и проверить заново"': 'text="♻️ Пересканировать"',
    }
    for old_value, new_value in replacements.items():
        replace(path, old_value, new_value)


def patch_compact_qwen_navigation() -> None:
    replacements = {
        'text="↩️ Velvet AI"': 'text="↩️ Qwen"',
        'text="🔄 Обновить статус"': 'text="🔄 Статус"',
        'text="🔁 Запустить ещё раз"': 'text="🔁 Повторить"',
        'text="📋 История AI"': 'text="📋 История"',
    }
    paths = [
        "velvet_bot/ai_jobs_ui.py",
        "velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_set_ai.py",
        "velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_calibration.py",
        "velvet_bot/presentation/telegram/routers/quality_operations_controllers/velvet_ai_formatting.py",
        "velvet_bot/presentation/telegram/routers/quality_operations_controllers/velvet_ai_visual.py",
        "velvet_bot/presentation/telegram/routers/references/comparison_help.py",
    ]
    for relative in paths:
        target = ROOT / relative
        text = target.read_text(encoding="utf-8")
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = text.replace('text="↩️ К аудиту"', 'text="↩️ Qwen"')
        text = text.replace('callback_data=quality_callback("menu")', 'callback_data=quality_callback("ai_menu")')
        target.write_text(text, encoding="utf-8")


def patch_public_download() -> None:
    path = "velvet_bot/domains/public_archive/repository.py"
    old = '''    async def resolve_download_source(
        self,
        *,
        character_id: int,
        media_id: int,
        member_access: bool,
    ) -> PublicDownloadSource | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    mf.telegram_file_id,
                    mf.source_telegram_file_id,
                    mf.watermark_applied,
                    mf.watermark_approved
                FROM character_media AS cm
                JOIN media_files AS mf ON mf.id = cm.media_id
                WHERE cm.character_id = $1::BIGINT
                  AND cm.media_id = $2::BIGINT
                  AND cm.is_public = TRUE
                """,
                int(character_id),
                int(media_id),
            )
'''
    new = '''    async def resolve_download_source(
        self,
        *,
        character_id: int,
        media_id: int,
        member_access: bool,
    ) -> PublicDownloadSource | None:
        visibility_sql = public_media_visibility_sql(
            include_adult_restricted=True,
            include_oversized_images=True,
        )
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                SELECT
                    mf.telegram_file_id,
                    mf.source_telegram_file_id,
                    mf.watermark_applied,
                    mf.watermark_approved
                FROM character_media AS cm
                JOIN media_files AS mf ON mf.id = cm.media_id
                WHERE cm.character_id = $1::BIGINT
                  AND cm.media_id = $2::BIGINT
                  AND ({visibility_sql})
                """,
                int(character_id),
                int(media_id),
            )
'''
    replace(path, old, new)


def main() -> None:
    patch_velvet_ai()
    patch_quality_operations()
    patch_rework_ui()
    patch_owner_menu()
    patch_quality_dashboard()
    patch_compact_qwen_navigation()
    patch_public_download()


if __name__ == "__main__":
    main()
