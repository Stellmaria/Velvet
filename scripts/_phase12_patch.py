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


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


replace_once(
    "velvet_bot/handlers/analytics_dashboard.py",
    "from aiogram.filters.callback_data import CallbackData\n",
    "",
)
replace_once(
    "velvet_bot/handlers/analytics_dashboard.py",
    "from velvet_bot.post_classification import POST_TYPE_LABELS\n",
    "from velvet_bot.post_classification import POST_TYPE_LABELS\n"
    "from velvet_bot.presentation.telegram.analytics_navigation import (\n"
    "    AnalyticsCallback,\n"
    "    _cb,\n"
    "    _period_row,\n"
    ")\n",
)
replace_once(
    "velvet_bot/handlers/analytics_dashboard.py",
    '''class AnalyticsCallback(CallbackData, prefix="dash"):\n    action: str\n    period: str = "all"\n    page: int = 0\n    source_id: int = 0\n\n\ndef _cb(\n    action: str,\n    *,\n    period: str = "all",\n    page: int = 0,\n    source_id: int = 0,\n) -> str:\n    return AnalyticsCallback(\n        action=action,\n        period=normalize_period(period),\n        page=max(0, page),\n        source_id=source_id,\n    ).pack()\n\n\n''',
    "",
)
replace_once(
    "velvet_bot/handlers/analytics_dashboard.py",
    '''def _period_row(action: str, period: str, *, source_id: int = 0) -> list[InlineKeyboardButton]:\n    labels = (("7d", "7 дней"), ("30d", "30 дней"), ("all", "Всё время"))\n    return [\n        InlineKeyboardButton(\n            text=("● " if key == period else "") + label,\n            callback_data=_cb(action, period=key, source_id=source_id),\n        )\n        for key, label in labels\n    ]\n\n\n''',
    "",
)

replace_once(
    "velvet_bot/handlers/analytics_discussion_overrides.py",
    "from velvet_bot.handlers.analytics_dashboard import AnalyticsCallback, _cb, _period_row\n",
    "from velvet_bot.discussion_queries import get_discussion_parent_channel_id\n"
    "from velvet_bot.presentation.telegram.analytics_navigation import (\n"
    "    AnalyticsCallback,\n"
    "    _cb,\n"
    "    _period_row,\n"
    ")\n",
)
replace_once(
    "velvet_bot/handlers/analytics_discussion_overrides.py",
    '''async def _resolve_parent_id(database: Database, chat_id: int) -> int | None:\n    async with database._require_pool().acquire() as connection:\n        value = await connection.fetchval(\n            """\n            SELECT parent_channel_id\n            FROM tracked_channels\n            WHERE chat_id = $1::BIGINT\n              AND source_kind = 'discussion'\n              AND enabled = TRUE\n            """,\n            int(chat_id),\n        )\n    return int(value) if value is not None else None\n\n\n''',
    '''async def _resolve_parent_id(database: Database, chat_id: int) -> int | None:\n    return await get_discussion_parent_channel_id(database, chat_id)\n\n\n''',
)

replace_once(
    "velvet_bot/domains/discussions/repository.py",
    "        return value is not None\n\n    async def set_reaction_counts(\n",
    '''        return value is not None\n\n    async def get_parent_channel_id(self, chat_id: int) -> int | None:\n        async with self._database._require_pool().acquire() as connection:\n            value = await connection.fetchval(\n                """\n                SELECT parent_channel_id\n                FROM tracked_channels\n                WHERE chat_id = $1::BIGINT\n                  AND source_kind = 'discussion'\n                  AND enabled = TRUE\n                """,\n                int(chat_id),\n            )\n        return int(value) if value is not None else None\n\n    async def set_reaction_counts(\n''',
)
replace_once(
    "velvet_bot/domains/discussions/service.py",
    "    async def is_tracked(self, chat_id: int) -> bool:\n        return await self._repository.is_tracked(chat_id)\n\n",
    '''    async def is_tracked(self, chat_id: int) -> bool:\n        return await self._repository.is_tracked(chat_id)\n\n    async def get_parent_channel_id(self, chat_id: int) -> int | None:\n        return await self._repository.get_parent_channel_id(chat_id)\n\n''',
)
replace_once(
    "velvet_bot/discussion_queries.py",
    "async def is_tracked_discussion(database: Database, chat_id: int) -> bool:\n    return await build_discussion_service(database).is_tracked(chat_id)\n\n\n",
    '''async def is_tracked_discussion(database: Database, chat_id: int) -> bool:\n    return await build_discussion_service(database).is_tracked(chat_id)\n\n\nasync def get_discussion_parent_channel_id(\n    database: Database,\n    chat_id: int,\n) -> int | None:\n    return await build_discussion_service(database).get_parent_channel_id(chat_id)\n\n\n''',
)
replace_once(
    "velvet_bot/discussion_queries.py",
    '    "get_discussion_overview",\n',
    '    "get_discussion_overview",\n    "get_discussion_parent_channel_id",\n',
)

write(
    "velvet_bot/presentation/telegram/analytics_navigation.py",
    '''from __future__ import annotations\n\nfrom aiogram.filters.callback_data import CallbackData\nfrom aiogram.types import InlineKeyboardButton\n\nfrom velvet_bot.analytics_dashboard import normalize_period\n\n\nclass AnalyticsCallback(CallbackData, prefix="dash"):\n    action: str\n    period: str = "all"\n    page: int = 0\n    source_id: int = 0\n\n\ndef _cb(\n    action: str,\n    *,\n    period: str = "all",\n    page: int = 0,\n    source_id: int = 0,\n) -> str:\n    return AnalyticsCallback(\n        action=action,\n        period=normalize_period(period),\n        page=max(0, page),\n        source_id=source_id,\n    ).pack()\n\n\ndef _period_row(\n    action: str,\n    period: str,\n    *,\n    source_id: int = 0,\n) -> list[InlineKeyboardButton]:\n    labels = (("7d", "7 дней"), ("30d", "30 дней"), ("all", "Всё время"))\n    return [\n        InlineKeyboardButton(\n            text=("● " if key == period else "") + label,\n            callback_data=_cb(action, period=key, source_id=source_id),\n        )\n        for key, label in labels\n    ]\n\n\n__all__ = ("AnalyticsCallback", "_cb", "_period_row")\n''',
)
write(
    "tests/test_phase12_discussion_navigation.py",
    '''from __future__ import annotations\n\nimport unittest\nfrom pathlib import Path\nfrom types import SimpleNamespace\nfrom unittest.mock import AsyncMock\n\nfrom velvet_bot.domains.discussions import DiscussionService\nfrom velvet_bot.presentation.telegram.analytics_navigation import (\n    AnalyticsCallback,\n    _cb,\n    _period_row,\n)\n\n\nROOT = Path(__file__).resolve().parents[1]\n\n\nclass DiscussionNavigationTests(unittest.IsolatedAsyncioTestCase):\n    async def test_parent_channel_lookup_is_delegated(self) -> None:\n        repository = SimpleNamespace(\n            get_parent_channel_id=AsyncMock(return_value=-1003802812639)\n        )\n        service = DiscussionService(repository)\n\n        result = await service.get_parent_channel_id(-1003859952761)\n\n        self.assertEqual(result, -1003802812639)\n        repository.get_parent_channel_id.assert_awaited_once_with(-1003859952761)\n\n    def test_navigation_contract_is_shared(self) -> None:\n        packed = _cb("menu", period="30d", page=-1, source_id=-1001)\n        unpacked = AnalyticsCallback.unpack(packed)\n        self.assertEqual(unpacked.period, "30d")\n        self.assertEqual(unpacked.page, 0)\n        self.assertEqual(len(_period_row("menu", "30d")), 3)\n        self.assertLessEqual(len(packed.encode("utf-8")), 64)\n\n    def test_discussion_handler_has_no_handler_import_or_sql(self) -> None:\n        source = (\n            ROOT / "velvet_bot/handlers/analytics_discussion_overrides.py"\n        ).read_text(encoding="utf-8")\n        self.assertNotIn("from velvet_bot.handlers.analytics_dashboard", source)\n        self.assertNotIn("database._require_pool()", source)\n        self.assertNotIn("SELECT parent_channel_id", source)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
)

(ROOT / "scripts/_phase12_patch.py").unlink()
(ROOT / ".github/workflows/phase12-patch.yml").unlink()
