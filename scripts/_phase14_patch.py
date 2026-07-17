from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "velvet_bot/handlers/analytics_management.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
LINES = SOURCE.splitlines()
TREE = ast.parse(SOURCE)
NODES = {
    node.name: node
    for node in TREE.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
}


def extract(name: str, *, decorators: bool = False) -> str:
    node = NODES[name]
    start = node.lineno
    if decorators and getattr(node, "decorator_list", None):
        start = min(item.lineno for item in node.decorator_list)
    return "\n".join(LINES[start - 1 : node.end_lineno]) + "\n"


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


common = '''from __future__ import annotations

from html import escape

from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.analytics_callbacks import dashboard_link, management_link
from velvet_bot.analytics_review import CharacterPickerItem, ReviewPage, list_character_picker
from velvet_bot.character_directory import category_label, universe_label
from velvet_bot.database import Database

'''
for name in (
    "_primary_channel_id",
    "_short",
    "_date",
    "_edit",
    "_pager",
    "_character_detail",
    "_show_character_picker",
):
    common += extract(name) + "\n"
common += '''__all__ = (
    "_character_detail",
    "_date",
    "_edit",
    "_pager",
    "_primary_channel_id",
    "_short",
    "_show_character_picker",
)
'''
write("velvet_bot/handlers/analytics_management_common.py", common)


tags = '''from __future__ import annotations

from html import escape

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.analytics_callbacks import AnalyticsManageCallback, dashboard_link, management_link
from velvet_bot.analytics_dashboard import PERIOD_LABELS
from velvet_bot.analytics_review import (
    UnresolvedTagReview,
    assign_unresolved_tag,
    get_unresolved_tag_review,
    list_unresolved_tag_reviews,
)
from velvet_bot.database import Database
from velvet_bot.handlers.analytics_management_common import (
    _edit,
    _pager,
    _short,
    _show_character_picker,
)

TAG_ACTIONS = frozenset({"unresolved", "tag", "tagchars", "tagassign"})

'''
for name in ("_show_unresolved_queue", "_show_tag_detail"):
    tags += extract(name) + "\n"
tags += '''async def handle_tag_action(
    callback: CallbackQuery,
    callback_data: AnalyticsManageCallback,
    database: Database,
    *,
    channel_id: int,
    period: str,
) -> bool:
    action = callback_data.action
    if action not in TAG_ACTIONS:
        return False

    if action == "unresolved":
        await _show_unresolved_queue(
            callback,
            database,
            channel_id=channel_id,
            period=period,
            page_number=callback_data.page,
        )
    elif action == "tag":
        await _show_tag_detail(
            callback,
            database,
            token_id=callback_data.token_id,
            period=period,
            return_page=callback_data.page,
        )
    elif action == "tagchars":
        await _show_character_picker(
            callback,
            database,
            action=action,
            period=period,
            page_number=callback_data.page,
            token_id=callback_data.token_id,
        )
    else:
        try:
            alias = await assign_unresolved_tag(
                database,
                token_id=callback_data.token_id,
                character_id=callback_data.character_id,
                changed_by=callback.from_user.id,
            )
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return True
        await _show_unresolved_queue(
            callback,
            database,
            channel_id=channel_id,
            period=period,
            page_number=0,
        )
        await callback.answer(
            f"#{alias.alias} назначен персонажу {alias.character_name}.",
            show_alert=True,
        )
        return True

    await callback.answer()
    return True


__all__ = ("TAG_ACTIONS", "handle_tag_action")
'''
write("velvet_bot/handlers/analytics_management_tags.py", tags)


aliases = '''from __future__ import annotations

import re
from html import escape

from aiogram.types import (
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.alias_management import (
    delete_character_alias_by_id,
    get_character_alias_summary,
)
from velvet_bot.analytics_callbacks import AnalyticsManageCallback, management_link
from velvet_bot.character_aliases import add_character_alias
from velvet_bot.database import Database
from velvet_bot.handlers.analytics_management_common import (
    _edit,
    _short,
    _show_character_picker,
)

_ALIAS_REPLY_RE = re.compile(r"ALIAS_CHARACTER:(\\d+)")
ALIAS_ACTIONS = frozenset(
    {"aliases", "aliaschar", "aliasadd", "aliasdel", "aliasdelok"}
)

'''
aliases += extract("_show_character_aliases") + "\n"
aliases += '''async def handle_alias_action(
    callback: CallbackQuery,
    callback_data: AnalyticsManageCallback,
    database: Database,
    *,
    period: str,
) -> bool:
    action = callback_data.action
    if action not in ALIAS_ACTIONS:
        return False

    if action == "aliases":
        await _show_character_picker(
            callback,
            database,
            action=action,
            period=period,
            page_number=callback_data.page,
        )
    elif action == "aliaschar":
        await _show_character_aliases(
            callback,
            database,
            character_id=callback_data.character_id,
            period=period,
            return_page=callback_data.page,
        )
    elif action == "aliasadd":
        name, _ = await get_character_alias_summary(
            database,
            character_id=callback_data.character_id,
        )
        if name is None or not isinstance(callback.message, Message):
            await callback.answer("Персонаж больше не найден.", show_alert=True)
            return True
        marker = f"ALIAS_CHARACTER:{callback_data.character_id}"
        await callback.message.answer(
            f"<b>Новый алиас: {escape(name)}</b>\n\n"
            "Ответьте на это сообщение новым вариантом хэштега без обязательного символа #.\n"
            "Пример: <code>KaelLang</code>\n\n"
            f"<code>{marker}</code>",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="KaelLang",
            ),
        )
        await callback.answer("Пришлите алиас ответом на сообщение.")
        return True
    elif action == "aliasdel":
        name, items = await get_character_alias_summary(
            database,
            character_id=callback_data.character_id,
        )
        item = next(
            (value for value in items if value.id == callback_data.alias_id),
            None,
        )
        if name is None or item is None or item.source == "name":
            await callback.answer("Алиас нельзя удалить.", show_alert=True)
            return True
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🗑 Да, удалить",
                        callback_data=management_link(
                            "aliasdelok",
                            period=period,
                            character_id=callback_data.character_id,
                            alias_id=item.id,
                            page=callback_data.page,
                        ),
                    ),
                    InlineKeyboardButton(
                        text="Отмена",
                        callback_data=management_link(
                            "aliaschar",
                            period=period,
                            character_id=callback_data.character_id,
                            page=callback_data.page,
                        ),
                    ),
                ]
            ]
        )
        await _edit(
            callback,
            f"Удалить алиас <code>#{escape(item.alias)}</code> у "
            f"<b>{escape(name)}</b>?\n\n"
            "Совпадающие старые хэштеги снова станут нераспознанными.",
            keyboard,
        )
    else:
        deleted = await delete_character_alias_by_id(
            database,
            alias_id=callback_data.alias_id,
        )
        if deleted is None:
            await callback.answer("Алиас уже удалён или защищён.", show_alert=True)
            return True
        await _show_character_aliases(
            callback,
            database,
            character_id=deleted.character_id,
            period=period,
            return_page=callback_data.page,
        )
        await callback.answer(f"Алиас #{deleted.alias} удалён.", show_alert=True)
        return True

    await callback.answer()
    return True


'''
reply = extract("handle_alias_reply")
reply = reply.replace(
    "async def handle_alias_reply(",
    "async def handle_alias_reply_message(",
    1,
)
aliases += reply + "\n"
aliases += '''__all__ = (
    "ALIAS_ACTIONS",
    "handle_alias_action",
    "handle_alias_reply_message",
)
'''
write("velvet_bot/handlers/analytics_management_aliases.py", aliases)


publications = '''from __future__ import annotations

from html import escape

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.analytics_callbacks import AnalyticsManageCallback, dashboard_link, management_link
from velvet_bot.analytics_dashboard import PERIOD_LABELS
from velvet_bot.analytics_review import (
    PublicationReview,
    get_publication_review,
    list_publication_reviews,
    reclassify_automatic_publications,
    reset_publication_type_to_automatic,
    set_manual_publication_type,
)
from velvet_bot.database import Database
from velvet_bot.handlers.analytics_management_common import _date, _edit, _pager, _short
from velvet_bot.post_classification import POST_TYPE_LABELS

_TYPE_BUTTON_LABELS = {
    "prompt": "📝 Промт",
    "art": "🖼 Арт",
    "announcement": "📣 Анонс",
    "giveaway": "🎁 Розыгрыш",
    "collaboration": "🤝 Совместная",
    "update": "🆕 Обновление",
    "service": "ℹ️ Служебный",
    "unknown": "❔ Не определено",
}
PUBLICATION_ACTIONS = frozenset({"review", "post", "ptype", "pauto", "reclassify"})

'''
for name in ("_publication_button", "_show_publication_queue", "_show_publication_detail"):
    publications += extract(name) + "\n"
publications += '''async def handle_publication_action(
    callback: CallbackQuery,
    callback_data: AnalyticsManageCallback,
    database: Database,
    *,
    channel_id: int,
    period: str,
) -> bool:
    action = callback_data.action
    if action not in PUBLICATION_ACTIONS:
        return False

    if action == "review":
        await _show_publication_queue(
            callback,
            database,
            channel_id=channel_id,
            period=period,
            page_number=callback_data.page,
            mode=callback_data.value or "low",
        )
    elif action == "post":
        await _show_publication_detail(
            callback,
            database,
            token_id=callback_data.token_id,
            period=period,
            return_page=callback_data.page,
            mode=callback_data.value or "low",
        )
    elif action == "ptype":
        mode, _, post_type = callback_data.value.partition("|")
        try:
            item = await set_manual_publication_type(
                database,
                token_id=callback_data.token_id,
                post_type=post_type,
                changed_by=callback.from_user.id,
            )
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return True
        await _show_publication_detail(
            callback,
            database,
            token_id=callback_data.token_id,
            period=period,
            return_page=callback_data.page,
            mode=mode or "low",
        )
        await callback.answer(
            f"Тип сохранён: {POST_TYPE_LABELS.get(item.post_type, item.post_type)}.",
            show_alert=True,
        )
        return True
    elif action == "pauto":
        try:
            item = await reset_publication_type_to_automatic(
                database,
                token_id=callback_data.token_id,
                changed_by=callback.from_user.id,
            )
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return True
        await _show_publication_detail(
            callback,
            database,
            token_id=callback_data.token_id,
            period=period,
            return_page=callback_data.page,
            mode=callback_data.value or "low",
        )
        await callback.answer(
            f"Автоматический тип: {POST_TYPE_LABELS.get(item.post_type, item.post_type)}.",
            show_alert=True,
        )
        return True
    else:
        await callback.answer("Пересчитываю автоматические типы…")
        changed, total = await reclassify_automatic_publications(
            database,
            channel_id=channel_id,
            changed_by=callback.from_user.id,
        )
        await _show_publication_queue(
            callback,
            database,
            channel_id=channel_id,
            period=period,
            page_number=0,
            mode="low",
        )
        if isinstance(callback.message, Message):
            await callback.message.answer(
                f"<b>Классификация пересчитана.</b>\n\n"
                f"Проверено публикаций: <b>{total}</b>\n"
                f"Изменилось: <b>{changed}</b>."
            )
        return True

    await callback.answer()
    return True


__all__ = ("PUBLICATION_ACTIONS", "handle_publication_action")
'''
write("velvet_bot/handlers/analytics_management_publications.py", publications)


facade = '''from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from velvet_bot.analytics_callbacks import AnalyticsManageCallback
from velvet_bot.analytics_dashboard import normalize_period
from velvet_bot.database import Database
from velvet_bot.handlers.analytics_management_aliases import (
    ALIAS_ACTIONS,
    handle_alias_action,
    handle_alias_reply_message,
)
from velvet_bot.handlers.analytics_management_common import _primary_channel_id
from velvet_bot.handlers.analytics_management_publications import (
    PUBLICATION_ACTIONS,
    handle_publication_action,
)
from velvet_bot.handlers.analytics_management_tags import TAG_ACTIONS, handle_tag_action

router = Router(name=__name__)


@router.callback_query(AnalyticsManageCallback.filter())
async def handle_analytics_management(
    callback: CallbackQuery,
    callback_data: AnalyticsManageCallback,
    database: Database,
    analytics_channel_ids: frozenset[int],
) -> None:
    action = callback_data.action
    period = normalize_period(callback_data.period)

    if action == "noop":
        await callback.answer()
        return

    if action in ALIAS_ACTIONS:
        await handle_alias_action(
            callback,
            callback_data,
            database,
            period=period,
        )
        return

    channel_id = _primary_channel_id(analytics_channel_ids)
    if action in TAG_ACTIONS or action in PUBLICATION_ACTIONS:
        if channel_id is None:
            await callback.answer(
                "Основной канал аналитики не настроен.",
                show_alert=True,
            )
            return

    if action in TAG_ACTIONS:
        await handle_tag_action(
            callback,
            callback_data,
            database,
            channel_id=channel_id,
            period=period,
        )
        return

    if action in PUBLICATION_ACTIONS:
        await handle_publication_action(
            callback,
            callback_data,
            database,
            channel_id=channel_id,
            period=period,
        )
        return

    await callback.answer("Неизвестное действие аналитики.", show_alert=True)


@router.message(F.reply_to_message.text.contains("ALIAS_CHARACTER:"))
async def handle_alias_reply(message: Message, database: Database) -> None:
    await handle_alias_reply_message(message, database)


__all__ = ("router",)
'''
write("velvet_bot/handlers/analytics_management.py", facade)


write(
    "tests/test_phase14_analytics_management_split.py",
    '''from __future__ import annotations

import importlib
import unittest
from pathlib import Path

from velvet_bot.handlers.analytics_management_aliases import ALIAS_ACTIONS
from velvet_bot.handlers.analytics_management_publications import PUBLICATION_ACTIONS
from velvet_bot.handlers.analytics_management_tags import TAG_ACTIONS


ROOT = Path(__file__).resolve().parents[1]


class AnalyticsManagementSplitTests(unittest.TestCase):
    def test_action_sets_do_not_overlap(self) -> None:
        self.assertFalse(TAG_ACTIONS & ALIAS_ACTIONS)
        self.assertFalse(TAG_ACTIONS & PUBLICATION_ACTIONS)
        self.assertFalse(ALIAS_ACTIONS & PUBLICATION_ACTIONS)
        self.assertEqual(
            TAG_ACTIONS | ALIAS_ACTIONS | PUBLICATION_ACTIONS,
            {
                "unresolved",
                "tag",
                "tagchars",
                "tagassign",
                "aliases",
                "aliaschar",
                "aliasadd",
                "aliasdel",
                "aliasdelok",
                "review",
                "post",
                "ptype",
                "pauto",
                "reclassify",
            },
        )

    def test_facade_is_small_and_importable(self) -> None:
        module = importlib.import_module("velvet_bot.handlers.analytics_management")
        self.assertIsNotNone(module.router)
        source = (
            ROOT / "velvet_bot/handlers/analytics_management.py"
        ).read_text(encoding="utf-8")
        self.assertLess(len(source.splitlines()), 100)
        self.assertNotIn("list_unresolved_tag_reviews", source)
        self.assertNotIn("set_manual_publication_type", source)
        self.assertNotIn("get_character_alias_summary", source)

    def test_domain_modules_are_separate(self) -> None:
        for path in (
            "analytics_management_tags.py",
            "analytics_management_aliases.py",
            "analytics_management_publications.py",
        ):
            self.assertTrue((ROOT / "velvet_bot/handlers" / path).is_file())


if __name__ == "__main__":
    unittest.main()
''',
)

(ROOT / "scripts/_phase14_patch.py").unlink()
(ROOT / ".github/workflows/phase14-patch.yml").unlink()
