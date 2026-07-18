from pathlib import Path

path = Path('velvet_bot/handlers/velvet_ai_formatting.py')
text = path.read_text(encoding='utf-8')

old_source = '''    try:
        source = await _source_text(message, bot)
    except Exception as error:
        await message.answer(f"Не удалось прочитать материал: <code>{escape(str(error))}</code>")
        return
'''
new_source = '''    try:
        source = await _source_text(message, bot)
    except (ValueError, RuntimeError) as error:
        await message.answer(f"Не удалось прочитать материал: <code>{escape(str(error))}</code>")
        return
'''
if text.count(old_source) != 1:
    raise SystemExit(f'unexpected source boundary count: {text.count(old_source)}')
text = text.replace(old_source, new_source, 1)

old_job = '    except ' + 'Exception as error:\n        logger.exception("Velvet formatting failed mode=%s job_id=%s", mode, tracker.job_id)\n'
new_job = '    except Exception as error:  # p2-approved-boundary: compensate-velvet-formatting-job\n        logger.exception("Velvet formatting failed mode=%s job_id=%s", mode, tracker.job_id)\n'
if text.count(old_job) != 1:
    raise SystemExit(f'unexpected formatting job boundary count: {text.count(old_job)}')
text = text.replace(old_job, new_job, 1)

path.write_text(text, encoding='utf-8')
