from pathlib import Path

path = Path("velvet_bot/handlers/quality_duplicates.py")
text = path.read_text(encoding="utf-8")
text = text.replace(
    "from aiogram.exceptions import TelegramAPIError\n",
    "from aiogram.exceptions import TelegramAPIError, TelegramBadRequest\n",
    1,
)
old = '''    except Exception as error:
        if "message is not modified" not in str(error).casefold():
            raise
'''
new = '''    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise
'''
if old not in text:
    raise SystemExit("safe edit catch not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
