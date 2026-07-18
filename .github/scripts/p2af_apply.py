from pathlib import Path

path = Path('velvet_bot/handlers/velvet_ai.py')
text = path.read_text(encoding='utf-8')
old = '    except ' + 'Exception as error:\n'
new = '    except Exception as error:  # p2-approved-boundary: compensate-prompt-result-job\n'
if text.count(old) != 1:
    raise SystemExit(f'unexpected broad catch count: {text.count(old)}')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
