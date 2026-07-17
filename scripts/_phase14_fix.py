from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {path}, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "velvet_bot/handlers/analytics_management_aliases.py",
    '''            f"<b>Новый алиас: {escape(name)}</b>

"
            "Ответьте на это сообщение новым вариантом хэштега без обязательного символа #.
"
            "Пример: <code>KaelLang</code>

"
            f"<code>{marker}</code>",
''',
    r'''            f"<b>Новый алиас: {escape(name)}</b>\n\n"
            "Ответьте на это сообщение новым вариантом хэштега без обязательного символа #.\n"
            "Пример: <code>KaelLang</code>\n\n"
            f"<code>{marker}</code>",
''',
)
replace_once(
    "velvet_bot/handlers/analytics_management_publications.py",
    '''                f"<b>Классификация пересчитана.</b>

"
                f"Проверено публикаций: <b>{total}</b>
"
                f"Изменилось: <b>{changed}</b>."
''',
    r'''                f"<b>Классификация пересчитана.</b>\n\n"
                f"Проверено публикаций: <b>{total}</b>\n"
                f"Изменилось: <b>{changed}</b>."
''',
)
replace_once(
    "velvet_bot/handlers/analytics_dashboard_overrides.py",
    "from velvet_bot.handlers.analytics_management import _show_unresolved_queue\n",
    "from velvet_bot.handlers.analytics_management_tags import _show_unresolved_queue\n",
)

(ROOT / "scripts/_phase14_fix.py").unlink()
(ROOT / ".github/workflows/phase14-fix.yml").unlink()
