from pathlib import Path

path = Path('velvet_bot/handlers/velvet_ai_visual.py')
text = path.read_text(encoding='utf-8')
old = '    except ' + 'Exception as error:\n        logger.exception("Palette/composition analysis failed job_id=%s", tracker.job_id)\n'
new = '    except Exception as error:  # p2-approved-boundary: compensate-palette-composition-job\n        logger.exception("Palette/composition analysis failed job_id=%s", tracker.job_id)\n'
if text.count(old) != 1:
    raise SystemExit(f'unexpected visual job boundary count: {text.count(old)}')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
