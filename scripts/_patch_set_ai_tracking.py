from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "velvet_bot/handlers/quality_set_ai.py"


def replace_span(source: str, start: str, end: str, replacement: str, *, label: str) -> str:
    start_index = source.find(start)
    if start_index < 0:
        raise RuntimeError(f"{label}: не найдена начальная граница")
    end_index = source.find(end, start_index + len(start))
    if end_index < 0:
        raise RuntimeError(f"{label}: не найдена конечная граница")
    return source[:start_index] + replacement + source[end_index:]


def main() -> None:
    source = PATH.read_text(encoding="utf-8")
    import_line = "from velvet_bot.ai_job_runtime import AIJobTracker\n"
    if import_line not in source:
        anchor = "from velvet_bot.core.config import load_settings\n"
        if source.count(anchor) != 1:
            raise RuntimeError("Не найдена точка импорта AIJobTracker")
        source = source.replace(anchor, import_line + anchor, 1)

    analyze_function = '''async def _analyze_set(
    database: Database,
    bot: Bot,
    *,
    set_id: int,
    created_by: int | None,
    tracker: AIJobTracker | None = None,
) -> tuple[MediaSetBundle, int, dict[str, object]]:
    bundle = await _load_set(database, set_id)
    if bundle is None:
        raise ValueError("Сет не найден.")
    if len(bundle.items) < 2:
        raise ValueError("В сете меньше двух доступных изображений.")
    if len(bundle.items) > 12:
        raise ValueError("Qwen проверяет не более 12 изображений за один сет.")

    settings = load_settings()
    if not settings.ai_vision_enabled:
        raise ValueError("Локальный Qwen отключён в настройках бота.")

    if tracker is not None:
        await tracker.stage("downloading")
    sources = await asyncio.gather(*(_download_item(bot, item) for item in bundle.items))
    inputs = tuple(
        SetConsistencyInput(
            media_id=item.media_id,
            image=source,
            characters=item.characters,
        )
        for item, source in zip(bundle.items, sources, strict=True)
    )
    client = SetConsistencyClient(
        provider=settings.ai_vision_provider,
        base_url=settings.ai_vision_base_url,
        model=settings.ai_vision_model,
        api_key=settings.ai_vision_api_key,
        timeout_seconds=settings.ai_vision_timeout_seconds,
    )
    if tracker is not None:
        await tracker.stage("analyzing")
    async with get_local_ai_lock():
        report = await client.analyze_set(inputs)
    if tracker is not None:
        await tracker.stage("saving")
    report_id = await _save_report(
        database,
        set_id=bundle.id,
        provider=client.provider,
        model=client.model,
        report=report,
        created_by=created_by,
    )
    return bundle, report_id, report
'''
    source = replace_span(
        source,
        "async def _analyze_set(\n",
        "\n\nasync def _send_set_media",
        analyze_function,
        label="set analysis function",
    )

    callback_handler = '''@router.callback_query(QualityCallback.filter(F.action == "setanalyze"))
async def handle_set_analyze(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
    bot: Bot,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    settings = load_settings()
    if not settings.ai_vision_enabled:
        await callback.answer("Локальный Qwen отключён в настройках бота.", show_alert=True)
        return
    tracker = await AIJobTracker.create(
        database=database,
        source_message=callback.message,
        kind="media_set_consistency",
        title=f"Целостность медиасета #{callback_data.item_id}",
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
        request_payload={"set_id": callback_data.item_id},
    )
    await callback.answer(f"AI-задание #{tracker.job_id} зарегистрировано.")
    try:
        bundle, report_id, report = await _analyze_set(
            database,
            bot,
            set_id=callback_data.item_id,
            created_by=callback.from_user.id,
            tracker=tracker,
        )
        rendered = _format_report(bundle, report_id, report)
        await tracker.ready(
            result_text=rendered,
            result_payload=report,
            reference_type="media_set_consistency_report",
            reference_id=report_id,
        )
    except asyncio.CancelledError:
        await tracker.error("Задание прервано остановкой процесса.")
        raise
    except Exception as error:
        logger.exception(
            "Set consistency analysis failed set_id=%s job_id=%s",
            callback_data.item_id,
            tracker.job_id,
        )
        await tracker.error(error)
        await _safe_edit(
            callback.message,
            f"<b>❌ Проверка сета #{callback_data.item_id} не завершена</b>\n\n"
            f"AI-задание: <b>#{tracker.job_id}</b>\n"
            "Подробная причина сохранена в истории AI-заданий.",
            _detail_keyboard(callback_data.item_id, page=callback_data.page),
        )
        return
    await _safe_edit(
        callback.message,
        rendered,
        _detail_keyboard(bundle.id, page=callback_data.page),
    )
'''
    source = replace_span(
        source,
        '@router.callback_query(QualityCallback.filter(F.action == "setanalyze"))\n',
        '\n\n@router.callback_query(QualityCallback.filter(F.action == "setphotos"))',
        callback_handler,
        label="set analyze callback",
    )

    command_handler = '''@router.message(Command("analyze_set", "qwen_set"))
async def handle_set_analysis_command(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
) -> None:
    if message.chat.type != ChatType.PRIVATE:
        await message.answer("Проверка целостности сета доступна в личном чате с ботом.")
        return
    raw = " ".join((command.args or "").split()).strip()
    try:
        set_id = int(raw)
    except ValueError:
        await message.answer(
            "Укажите числовой ID сета.\n\n"
            "Пример: <code>/analyze_set 12</code>"
        )
        return
    if set_id <= 0:
        await message.answer("ID сета должен быть положительным числом.")
        return
    settings = load_settings()
    if not settings.ai_vision_enabled:
        await message.answer("Локальный Qwen отключён в настройках бота.")
        return
    tracker = await AIJobTracker.create(
        database=database,
        source_message=message,
        kind="media_set_consistency",
        title=f"Целостность медиасета #{set_id}",
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
        request_payload={"set_id": set_id, "source": "slash_command"},
    )
    try:
        bundle, report_id, report = await _analyze_set(
            database,
            bot,
            set_id=set_id,
            created_by=message.from_user.id if message.from_user else None,
            tracker=tracker,
        )
        rendered = _format_report(bundle, report_id, report)
        await tracker.ready(
            result_text=rendered,
            result_payload=report,
            reference_type="media_set_consistency_report",
            reference_id=report_id,
        )
    except asyncio.CancelledError:
        await tracker.error("Задание прервано остановкой процесса.")
        raise
    except Exception as error:
        logger.exception("Set consistency command failed set_id=%s job_id=%s", set_id, tracker.job_id)
        await tracker.error(error)
'''
    source = replace_span(
        source,
        '@router.message(Command("analyze_set", "qwen_set"))\n',
        '\n\n__all__ = ("router",)',
        command_handler,
        label="set analyze command",
    )

    ast.parse(source, filename=str(PATH))
    PATH.write_text(source, encoding="utf-8")


if __name__ == "__main__":
    main()
