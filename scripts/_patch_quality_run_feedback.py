from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "velvet_bot/handlers/quality_operations.py"
# The callback must be acknowledged before the potentially long worker cycle.

OLD = '''@router.callback_query(QualityCallback.filter(F.action == "quality_run"))
async def handle_quality_run(
    callback: CallbackQuery,
    database: Database,
    worker_manager: WorkerManager,
) -> None:
    try:
        ok = await worker_manager.run_now("ai-quality")
    except (RuntimeError, ValueError) as error:
        await callback.answer(str(error)[:190], show_alert=True)
        return
    if isinstance(callback.message, Message):
        await _show_menu(callback.message, database, worker_manager)
    await callback.answer(
        "Цикл проверки завершён." if ok else "Цикл завершился ошибкой. Откройте очередь ошибок.",
        show_alert=not ok,
    )
'''

NEW = '''@router.callback_query(QualityCallback.filter(F.action == "quality_run"))
async def handle_quality_run(
    callback: CallbackQuery,
    database: Database,
    worker_manager: WorkerManager,
) -> None:
    await callback.answer("Запускаю цикл проверки качества.")
    try:
        ok = await worker_manager.run_now("ai-quality")
    except (RuntimeError, ValueError) as error:
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "<b>❌ Проверка качества не запущена</b>\n\n"
                f"<code>{escape(str(error))[:900]}</code>"
            )
        return
    if isinstance(callback.message, Message):
        await _show_menu(callback.message, database, worker_manager)
        await callback.message.answer(
            "<b>✅ Цикл проверки качества завершён</b>"
            if ok
            else (
                "<b>❌ Цикл проверки завершился ошибкой</b>\n\n"
                "Подробности находятся в очереди ошибок и центре инцидентов."
            )
        )
'''


def main() -> None:
    source = PATH.read_text(encoding="utf-8")
    if source.count(OLD) != 1:
        raise RuntimeError("Не найден однозначный handler quality_run")
    source = source.replace(OLD, NEW, 1)
    ast.parse(source, filename=str(PATH))
    PATH.write_text(source, encoding="utf-8")


if __name__ == "__main__":
    main()
