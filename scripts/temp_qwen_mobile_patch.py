from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_in_file(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected text not found in {path}: {old!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def main() -> None:
    path = ROOT / "velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_operations.py"
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"def build_quality_operations_menu\(.*?\n    return text, keyboard\n",
        re.DOTALL,
    )
    replacement = r'''def build_quality_operations_menu(
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
    updated, count = pattern.subn(lambda _match: replacement, text)
    if count != 1:
        raise RuntimeError(f"Expected one quality menu block, got {count}")
    path.write_text(updated, encoding="utf-8")

    rework_test = ROOT / "tests/test_media_rework_queue.py"
    rework_text = rework_test.read_text(encoding="utf-8")
    rework_text = rework_text.replace("Вернуть на проверку Qwen", "Qwen-проверка")
    rework_test.write_text(rework_text, encoding="utf-8")

    quality_ui = ROOT / "velvet_bot/quality_ui.py"
    quality_text = quality_ui.read_text(encoding="utf-8")
    for old, new in {
        "👥 Категория ·": "👥 Без категории ·",
        "🌌 Вселенная ·": "🌌 Без вселенной ·",
        "📖 История ·": "📖 Без истории ·",
        "📦 Пустые ·": "📦 Без материалов ·",
    }.items():
        quality_text = quality_text.replace(old, new)
    quality_ui.write_text(quality_text, encoding="utf-8")

    retry_test = ROOT / "tests/test_qwen_duplicate_retry_controls.py"
    retry_text = retry_test.read_text(encoding="utf-8")
    retry_text = retry_text.replace(
        "from velvet_bot.domains.media_quality.models import DuplicatePage\n",
        "from velvet_bot.domains.media_quality.models import DuplicatePage\n"
        "from velvet_bot.domains.media_rework import MediaReworkSummary\n",
    )
    retry_text = retry_text.replace(
        "from velvet_bot.quality_ui import QualityCallback, build_duplicate_list, build_quality_dashboard\n",
        "from velvet_bot.quality_ui import QualityCallback, build_duplicate_list, build_quality_dashboard\n"
        "from velvet_bot.velvet_ai_ui import build_velvet_ai_menu\n",
    )
    old_method = '''    def test_quality_dashboard_exposes_qwen_retry_button(self) -> None:
        summary = QualitySummary(
            pending_duplicates=0,
            confirmed_duplicates=0,
            pending_scans=0,
            scan_errors=0,
            broken_files=0,
            unchecked_files=0,
            missing_category=0,
            missing_universe=0,
            missing_story=0,
            empty_characters=0,
            media_without_prompt=0,
            orphan_media=0,
            unresolved_hashtags=0,
        )
        ai_summary = AIQualitySummary(
            pending=0,
            processing=0,
            ready=0,
            errors=2,
            skipped=1,
            unreviewed=0,
            accepted=0,
            fix_required=0,
            clean=0,
            warnings=0,
            critical=0,
        )

        _, keyboard = build_quality_dashboard(summary, ai_summary)
        actions = {
            QualityCallback.unpack(button.callback_data).action
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        }

        self.assertIn("quality_retry_errors", actions)
'''
    new_method = '''    def test_qwen_panel_exposes_retry_and_audit_links_to_panel(self) -> None:
        summary = QualitySummary(
            pending_duplicates=0,
            confirmed_duplicates=0,
            pending_scans=0,
            scan_errors=0,
            broken_files=0,
            unchecked_files=0,
            missing_category=0,
            missing_universe=0,
            missing_story=0,
            empty_characters=0,
            media_without_prompt=0,
            orphan_media=0,
            unresolved_hashtags=0,
        )
        ai_summary = AIQualitySummary(
            pending=0,
            processing=0,
            ready=0,
            errors=2,
            skipped=1,
            unreviewed=0,
            accepted=0,
            fix_required=0,
            clean=0,
            warnings=0,
            critical=0,
        )
        rework_summary = MediaReworkSummary(
            active=0,
            needs_fix=0,
            checking=0,
            ready_for_review=0,
            stel_priority=0,
            qwen_only=0,
        )

        _, audit_keyboard = build_quality_dashboard(summary, ai_summary)
        _, qwen_keyboard = build_velvet_ai_menu(
            enabled=True,
            provider="ollama",
            model="qwen3-vl:8b",
            quality=ai_summary,
            rework=rework_summary,
        )
        audit_actions = {
            QualityCallback.unpack(button.callback_data).action
            for row in audit_keyboard.inline_keyboard
            for button in row
            if button.callback_data and button.callback_data.startswith("quality:")
        }
        qwen_actions = {
            QualityCallback.unpack(button.callback_data).action
            for row in qwen_keyboard.inline_keyboard
            for button in row
            if button.callback_data and button.callback_data.startswith("quality:")
        }

        self.assertIn("ai_menu", audit_actions)
        self.assertIn("quality_retry_errors", qwen_actions)
'''
    if old_method not in retry_text:
        raise RuntimeError("Old Qwen retry dashboard test block was not found")
    retry_test.write_text(retry_text.replace(old_method, new_method), encoding="utf-8")


if __name__ == "__main__":
    main()
