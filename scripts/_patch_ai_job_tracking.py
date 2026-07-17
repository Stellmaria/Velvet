from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(source: str, old: str, new: str, *, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: ожидалось одно совпадение, найдено {count}")
    return source.replace(old, new, 1)


def patch_prompt_result() -> None:
    path = ROOT / "velvet_bot/handlers/velvet_ai.py"
    source = path.read_text(encoding="utf-8")
    source = replace_once(
        source,
        "from velvet_bot.core.config import load_settings\n",
        "from velvet_bot.ai_job_runtime import AIJobTracker\n"
        "from velvet_bot.core.config import load_settings\n",
        label="prompt import",
    )
    old = '''    status = await message.answer(
        "<b>🧠 Qwen сравнивает промт и результат</b>\n\n"
        "Проверяю персонажей, композицию, свет, палитру, окружение и стиль."
    )
    file_id, file_unique_id = result_file
    try:
        image = await _download_image(bot, file_id)
        client = PromptResultComparisonClient(
            provider=settings.ai_vision_provider,
            base_url=settings.ai_vision_base_url,
            model=settings.ai_vision_model,
            api_key=settings.ai_vision_api_key,
            timeout_seconds=settings.ai_vision_timeout_seconds,
        )
        async with get_local_ai_lock():
            report = await client.compare(session.prompt_text, image)
        report_id = await PromptResultReportRepository(database).save(
            result_file_id=file_id,
            result_file_unique_id=file_unique_id,
            prompt_text=session.prompt_text,
            provider=client.provider,
            model=client.model,
            report=report,
            created_by=message.from_user.id if message.from_user else None,
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.exception("Prompt/result comparison failed")
        await status.edit_text(
            "<b>❌ Проверка промта не завершена</b>\n\n"
            f"<code>{escape(str(error))}</code>\n\n"
            "Промт сохранён до истечения формы, поэтому изображение можно отправить повторно."
        )
        return

    _sessions.pop(key, None)
    await status.edit_text(
        _report_text(report_id, report),
        reply_markup=_report_keyboard(),
    )
'''
    new = '''    file_id, file_unique_id = result_file
    tracker = await AIJobTracker.create(
        database=database,
        source_message=message,
        kind="prompt_result",
        title="Промт против результата",
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
        request_payload={
            "result_file_id": file_id,
            "result_file_unique_id": file_unique_id,
            "prompt_length": len(session.prompt_text),
        },
    )
    try:
        await tracker.stage("downloading")
        image = await _download_image(bot, file_id)
        client = PromptResultComparisonClient(
            provider=settings.ai_vision_provider,
            base_url=settings.ai_vision_base_url,
            model=settings.ai_vision_model,
            api_key=settings.ai_vision_api_key,
            timeout_seconds=settings.ai_vision_timeout_seconds,
        )
        await tracker.stage("analyzing")
        async with get_local_ai_lock():
            report = await client.compare(session.prompt_text, image)
        await tracker.stage("saving")
        report_id = await PromptResultReportRepository(database).save(
            result_file_id=file_id,
            result_file_unique_id=file_unique_id,
            prompt_text=session.prompt_text,
            provider=client.provider,
            model=client.model,
            report=report,
            created_by=message.from_user.id if message.from_user else None,
        )
        rendered = _report_text(report_id, report)
        await tracker.ready(
            result_text=rendered,
            result_payload=report,
            reference_type="prompt_result_report",
            reference_id=report_id,
        )
    except asyncio.CancelledError:
        await tracker.error("Задание прервано остановкой процесса.")
        raise
    except Exception as error:
        logger.exception("Prompt/result comparison failed job_id=%s", tracker.job_id)
        await tracker.error(error)
        return

    _sessions.pop(key, None)
'''
    source = replace_once(source, old, new, label="prompt flow")
    path.write_text(source, encoding="utf-8")


def patch_palette() -> None:
    path = ROOT / "velvet_bot/handlers/velvet_ai_visual.py"
    source = path.read_text(encoding="utf-8")
    source = replace_once(
        source,
        "from velvet_bot.core.config import load_settings\n",
        "from velvet_bot.ai_job_runtime import AIJobTracker\n"
        "from velvet_bot.core.config import load_settings\n",
        label="palette import",
    )
    old = '''    status = await message.answer(
        "<b>🧠 Qwen анализирует композицию</b>\n\n"
        "Измеряю палитру и проверяю фокус, баланс, кадрирование, глубину и свет."
    )
    file_id, file_unique_id = result_file
    try:
        image = await _download_image(bot, file_id)
        metrics = await asyncio.to_thread(extract_palette_metrics, image)
        client = CompositionAnalysisClient(
            provider=settings.ai_vision_provider,
            base_url=settings.ai_vision_base_url,
            model=settings.ai_vision_model,
            api_key=settings.ai_vision_api_key,
            timeout_seconds=settings.ai_vision_timeout_seconds,
        )
        async with get_local_ai_lock():
            report = await client.analyze_composition(image, metrics)
        report_id = await PaletteCompositionReportRepository(database).save(
            result_file_id=file_id,
            result_file_unique_id=file_unique_id,
            provider=client.provider,
            model=client.model,
            metrics=metrics,
            report=report,
            created_by=message.from_user.id if message.from_user else None,
        )
        palette_card = await asyncio.to_thread(build_palette_card, metrics)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.exception("Palette/composition analysis failed")
        await status.edit_text(
            "<b>❌ Анализ палитры и композиции не завершён</b>\n\n"
            f"<code>{escape(str(error))}</code>"
        )
        return
    await status.edit_text(
        _report_text(report_id, metrics, report),
        reply_markup=_report_keyboard(),
    )
'''
    new = '''    file_id, file_unique_id = result_file
    tracker = await AIJobTracker.create(
        database=database,
        source_message=message,
        kind="palette_composition",
        title="Палитра и композиция",
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
        request_payload={
            "result_file_id": file_id,
            "result_file_unique_id": file_unique_id,
        },
    )
    try:
        await tracker.stage("downloading")
        image = await _download_image(bot, file_id)
        await tracker.stage("preparing")
        metrics = await asyncio.to_thread(extract_palette_metrics, image)
        client = CompositionAnalysisClient(
            provider=settings.ai_vision_provider,
            base_url=settings.ai_vision_base_url,
            model=settings.ai_vision_model,
            api_key=settings.ai_vision_api_key,
            timeout_seconds=settings.ai_vision_timeout_seconds,
        )
        await tracker.stage("analyzing")
        async with get_local_ai_lock():
            report = await client.analyze_composition(image, metrics)
        await tracker.stage("saving")
        report_id = await PaletteCompositionReportRepository(database).save(
            result_file_id=file_id,
            result_file_unique_id=file_unique_id,
            provider=client.provider,
            model=client.model,
            metrics=metrics,
            report=report,
            created_by=message.from_user.id if message.from_user else None,
        )
        palette_card = await asyncio.to_thread(build_palette_card, metrics)
        rendered = _report_text(report_id, metrics, report)
        await tracker.ready(
            result_text=rendered,
            result_payload=report,
            reference_type="palette_composition_report",
            reference_id=report_id,
        )
    except asyncio.CancelledError:
        await tracker.error("Задание прервано остановкой процесса.")
        raise
    except Exception as error:
        logger.exception("Palette/composition analysis failed job_id=%s", tracker.job_id)
        await tracker.error(error)
        return
'''
    source = replace_once(source, old, new, label="palette flow")
    path.write_text(source, encoding="utf-8")


def patch_formatting() -> None:
    path = ROOT / "velvet_bot/handlers/velvet_ai_formatting.py"
    source = path.read_text(encoding="utf-8")
    source = replace_once(
        source,
        "from velvet_bot.core.config import load_settings\n",
        "from velvet_bot.ai_job_runtime import AIJobTracker\n"
        "from velvet_bot.core.config import load_settings\n",
        label="format import",
    )
    old = '''    status = await message.answer(
        f"<b>🧠 Qwen · {_MODE_LABELS[mode]}</b>\n\n"
        "Собираю фирменную структуру и проверяю лимит Telegram."
    )
    try:
        client = VelvetFormattingClient(
            provider=settings.ai_vision_provider,
            base_url=settings.ai_vision_base_url,
            model=settings.ai_vision_model,
            api_key=settings.ai_vision_api_key,
            timeout_seconds=settings.ai_vision_timeout_seconds,
        )
        async with get_local_ai_lock():
            payload = await client.format(mode, source)
        rendered = render_velvet_post(mode, source, payload)
        await VelvetFormattingReportRepository(database).save(
            mode=mode,
            source_text=source,
            provider=client.provider,
            model=client.model,
            payload=payload,
            rendered_text=rendered,
            created_by=message.from_user.id if message.from_user else None,
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.exception("Velvet formatting failed mode=%s", mode)
        await status.edit_text(
            "<b>❌ Оформление не завершено</b>\n\n"
            f"<code>{escape(str(error))}</code>"
        )
        return

    await status.edit_text(rendered, reply_markup=_result_keyboard(mode))
'''
    new = '''    tracker = await AIJobTracker.create(
        database=database,
        source_message=message,
        kind="velvet_formatting",
        title=f"Оформление Velvet Anatomy · {_MODE_LABELS[mode]}",
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
        request_payload={"mode": mode, "source_length": len(source)},
    )
    try:
        client = VelvetFormattingClient(
            provider=settings.ai_vision_provider,
            base_url=settings.ai_vision_base_url,
            model=settings.ai_vision_model,
            api_key=settings.ai_vision_api_key,
            timeout_seconds=settings.ai_vision_timeout_seconds,
        )
        await tracker.stage("analyzing")
        async with get_local_ai_lock():
            payload = await client.format(mode, source)
        await tracker.stage("saving")
        rendered = render_velvet_post(mode, source, payload)
        report_id = await VelvetFormattingReportRepository(database).save(
            mode=mode,
            source_text=source,
            provider=client.provider,
            model=client.model,
            payload=payload,
            rendered_text=rendered,
            created_by=message.from_user.id if message.from_user else None,
        )
        await tracker.ready(
            result_text=rendered,
            result_payload=payload,
            reference_type="velvet_formatting_report",
            reference_id=report_id,
        )
    except asyncio.CancelledError:
        await tracker.error("Задание прервано остановкой процесса.")
        raise
    except Exception as error:
        logger.exception("Velvet formatting failed mode=%s job_id=%s", mode, tracker.job_id)
        await tracker.error(error)
        return
'''
    source = replace_once(source, old, new, label="format flow")
    path.write_text(source, encoding="utf-8")


def main() -> None:
    patch_prompt_result()
    patch_palette()
    patch_formatting()
    for relative in (
        "velvet_bot/handlers/velvet_ai.py",
        "velvet_bot/handlers/velvet_ai_visual.py",
        "velvet_bot/handlers/velvet_ai_formatting.py",
    ):
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


if __name__ == "__main__":
    main()
