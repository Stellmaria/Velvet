from pathlib import Path

path = Path('velvet_bot/services/system_health.py')
text = path.read_text(encoding='utf-8')
old = '        except ' + 'Exception as error:\n'
first = '        except Exception as error:  # p2-approved-boundary: capture-database-health-probe\n'
second = '        except Exception as error:  # p2-approved-boundary: capture-telegram-health-probe\n'
if text.count(old) != 2:
    raise SystemExit(f'unexpected system-health broad catch count: {text.count(old)}')
text = text.replace(old, first, 1)
text = text.replace(old, second, 1)
path.write_text(text, encoding='utf-8')
