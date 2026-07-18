from pathlib import Path

path = Path('velvet_bot/handlers/supervisor_console.py')
text = path.read_text(encoding='utf-8')
old = '    except ' + 'Exception:\n        # The command continues inside Supervisor even if Telegram editing fails.\n'
new = '    except Exception:  # p2-approved-boundary: isolate-supervisor-console-watcher\n        # The command continues inside Supervisor even if Telegram editing fails.\n'
if text.count(old) != 1:
    raise SystemExit(f'unexpected watcher broad catch count: {text.count(old)}')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
