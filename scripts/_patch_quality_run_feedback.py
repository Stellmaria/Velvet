from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "velvet_bot/handlers/quality_operations.py"
START = '@router.callback_query(QualityCallback.filter(F.action == "quality_run"))\n'
END = '\n\n__all__ = (\n'

NEW = r'''@router.callback_query(QualityCallback.filter(F.action == "quality_run"))
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
    start_index = source.find(START)
    if start_index < 0:
        raise RuntimeError("Не найден handler quality_run")
    end_index = source.find(END, start_index)
    if end_index < 0:
        raise RuntimeError("Не найден конец handler quality_run")
    source = source[:start_index] + NEW + source[end_index:]
    ast.parse(source, filename=str(PATH))
    PATH.write_text(source, encoding="utf-8")


if __name__ == "__main__":
    main()
