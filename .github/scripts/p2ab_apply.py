from pathlib import Path

path = Path("velvet_bot/handlers/quality_sets.py")
text = path.read_text(encoding="utf-8")
old = "    except " + "Exception as error:\n        if \"message is not modified\" not in str(error).casefold():\n            raise\n"
new = "    except TelegramBadRequest as error:\n        if \"message is not modified\" not in str(error).casefold():\n            raise\n"
if text.count(old) != 1:
    raise SystemExit(f"expected one safe-edit broad catch, found {text.count(old)}")
path.write_text(text.replace(old, new), encoding="utf-8")
