from pathlib import Path

path = Path('velvet_bot/infrastructure/telegram/archive_previews.py')
text = path.read_text(encoding='utf-8')
old = '        except ' + 'Exception as error:\n            logger.info(\n                "Could not prepare full-quality image media_id=%s: %s",\n'
new = '        except Exception as error:  # p2-approved-boundary: fallback-full-quality-archive-preview\n            logger.info(\n                "Could not prepare full-quality image media_id=%s: %s",\n'
if text.count(old) != 1:
    raise SystemExit(f'unexpected archive preview boundary count: {text.count(old)}')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
