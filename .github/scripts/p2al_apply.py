from pathlib import Path

path = Path('velvet_bot/public_archive_display.py')
text = path.read_text(encoding='utf-8')
needle = 'except ' + 'Exception'
first = '        ' + needle + ':\n            logger.exception("Failed to prepare compressed public image preview")\n'
first_new = '        except Exception:  # p2-approved-boundary: fallback-viewer-edit-preview\n            logger.exception("Failed to prepare compressed public image preview")\n'
second = '        ' + needle + ':\n            logger.exception("Compressed public preview generation failed")\n'
second_new = '        except Exception:  # p2-approved-boundary: fallback-viewer-send-preview\n            logger.exception("Compressed public preview generation failed")\n'
for old, new in ((first, first_new), (second, second_new)):
    if text.count(old) != 1:
        raise SystemExit(f'unexpected boundary count for {old!r}: {text.count(old)}')
    text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8')
