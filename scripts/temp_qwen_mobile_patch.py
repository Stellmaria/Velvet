from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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

    test_path = ROOT / "tests/test_media_rework_queue.py"
    test_text = test_path.read_text(encoding="utf-8")
    test_text = test_text.replace(
        "Вернуть на проверку Qwen",
        "Qwen-проверка",
    )
    test_path.write_text(test_text, encoding="utf-8")


if __name__ == "__main__":
    main()
