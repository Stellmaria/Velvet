from pathlib import Path

path = Path('velvet_bot/services/media_save.py')
text = path.read_text(encoding='utf-8')
old = '    except ' + 'Exception as error:\n'
outer = '    except Exception as error:  # p2-approved-boundary: report-media-save-failure\n'
topic = '    except Exception as error:  # p2-approved-boundary: isolate-media-topic-delivery\n'
if text.count(old) != 2:
    raise SystemExit(f'unexpected media-save broad catch count: {text.count(old)}')
text = text.replace(old, outer, 1)
text = text.replace(old, topic, 1)
path.write_text(text, encoding='utf-8')
