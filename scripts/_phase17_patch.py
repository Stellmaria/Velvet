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
    "velvet_bot/analytics_review.py",
    '''async def set_manual_publication_type(\n    database: Database,\n    *,\n    token_id: int,\n    post_type: str,\n    changed_by: int | None,\n) -> PublicationReview:\n    if post_type not in POST_TYPE_LABELS:\n        raise ValueError("Неизвестный тип публикации.")\n    item = await get_publication_review(database, token_id=token_id)\n    if item is None:\n        raise ValueError("Публикация больше не найдена.")\n    async with database._require_pool().acquire() as connection:\n        async with connection.transaction():\n            await _record_classification_change(\n                connection,\n                channel_id=await connection.fetchval(\n                    "SELECT channel_id FROM analytics_review_items WHERE id = $1",\n                    token_id,\n                ),\n                publication_key=item.publication_key,\n                previous_type=item.post_type,\n                new_type=post_type,\n                previous_confidence=item.confidence,\n                new_confidence=100,\n                previous_source=item.source,\n                new_source="manual",\n                changed_by=changed_by,\n                reason="ручной выбор в аналитическом центре",\n            )\n            channel_id = int(\n                await connection.fetchval(\n                    "SELECT channel_id FROM analytics_review_items WHERE id = $1",\n                    token_id,\n                )\n            )\n            await connection.execute(\n                """\n                UPDATE channel_posts\n                SET post_type = $3,\n                    post_type_confidence = 100,\n                    post_type_source = 'manual',\n                    is_prompt = ($3 = 'prompt'),\n                    updated_at = NOW()\n                WHERE channel_id = $1 AND publication_key = $2\n                """,\n                channel_id,\n                item.publication_key,\n                post_type,\n            )\n    refreshed = await get_publication_review(database, token_id=token_id)\n    if refreshed is None:\n        raise RuntimeError("Публикация исчезла после обновления.")\n    return refreshed\n''',
    '''async def set_manual_publication_type(\n    database: Database,\n    *,\n    token_id: int,\n    post_type: str,\n    changed_by: int | None,\n) -> PublicationReview:\n    if post_type not in POST_TYPE_LABELS:\n        raise ValueError("Неизвестный тип публикации.")\n    item = await get_publication_review(database, token_id=token_id)\n    if item is None:\n        raise ValueError("Публикация больше не найдена.")\n\n    async with database._require_pool().acquire() as connection:\n        async with connection.transaction():\n            channel_id = int(\n                await connection.fetchval(\n                    """\n                    SELECT channel_id\n                    FROM analytics_review_items\n                    WHERE id = $1::BIGINT\n                    """,\n                    token_id,\n                )\n            )\n            await _record_classification_change(\n                connection,\n                channel_id=channel_id,\n                publication_key=item.publication_key,\n                previous_type=item.post_type,\n                new_type=post_type,\n                previous_confidence=item.confidence,\n                new_confidence=100,\n                previous_source=item.source,\n                new_source="manual",\n                changed_by=changed_by,\n                reason="ручной выбор в аналитическом центре",\n            )\n            await connection.execute(\n                """\n                UPDATE channel_posts\n                SET post_type = $3::VARCHAR,\n                    post_type_confidence = 100,\n                    post_type_source = 'manual',\n                    is_prompt = ($3::VARCHAR = 'prompt'::VARCHAR),\n                    updated_at = NOW()\n                WHERE channel_id = $1::BIGINT\n                  AND publication_key = $2::VARCHAR\n                """,\n                channel_id,\n                item.publication_key,\n                post_type,\n            )\n\n    refreshed = await get_publication_review(database, token_id=token_id)\n    if refreshed is None:\n        raise RuntimeError("Публикация исчезла после обновления.")\n    return refreshed\n''',
)

replace_once(
    "velvet_bot/handlers/analytics_dashboard.py",
    '''from velvet_bot.presentation.telegram.analytics_navigation import (\n    AnalyticsCallback,\n    _cb,\n    _period_row,\n)\n''',
    '''from velvet_bot.presentation.telegram.analytics_navigation import (\n    AnalyticsCallback,\n    _cb,\n    _period_row,\n)\nfrom velvet_bot.safe_analytics_edit import safe_analytics_edit as _edit\n''',
)
replace_once(
    "velvet_bot/handlers/analytics_dashboard.py",
    '''async def _edit(callback: CallbackQuery, text: str, keyboard: InlineKeyboardMarkup) -> None:\n    if not isinstance(callback.message, Message):\n        await callback.answer("Меню больше недоступно.", show_alert=True)\n        return\n    await callback.message.edit_text(text, reply_markup=keyboard)\n\n\n''',
    "",
)

replace_once(
    "velvet_bot/handlers/public_manager.py",
    '''router = Router(name=__name__)\nlogger = logging.getLogger(__name__)\n_ACTIONS = {\n''',
    '''router = Router(name=__name__)\nlogger = logging.getLogger(__name__)\n\n\nclass _ArchiveDeleteNoiseFilter(logging.Filter):\n    def filter(self, record: logging.LogRecord) -> bool:\n        if record.getMessage() == "Could not delete archive topic message":\n            record.levelno = logging.INFO\n            record.levelname = "INFO"\n            record.msg = "Archive topic message was already absent or cannot be deleted"\n            record.args = ()\n        return True\n\n\nlogger.addFilter(_ArchiveDeleteNoiseFilter())\n\n_ACTIONS = {\n''',
)

write(
    "velvet_bot/runtime_log_hotfixes.py",
    '''from __future__ import annotations\n\nfrom velvet_bot.analytics_review import set_manual_publication_type\nfrom velvet_bot.media_quality import (\n    _claim_pending_images as claim_pending_images,\n    decide_duplicate_candidate,\n    scan_media_target,\n)\n\n\ndef install_runtime_log_hotfixes() -> None:\n    """Compatibility no-op: fixes now live in canonical modules."""\n\n\n__all__ = (\n    "claim_pending_images",\n    "decide_duplicate_candidate",\n    "install_runtime_log_hotfixes",\n    "scan_media_target",\n    "set_manual_publication_type",\n)\n''',
)

replace_once(
    "velvet_bot/safe_analytics_edit.py",
    '''def install_safe_analytics_edit() -> None:\n    from velvet_bot.handlers import analytics_dashboard\n\n    analytics_dashboard._edit = safe_analytics_edit\n''',
    '''def install_safe_analytics_edit() -> None:\n    """Compatibility no-op: handlers import the safe editor explicitly."""\n''',
)

write(
    "velvet_bot/presentation/telegram/compat.py",
    '''from __future__ import annotations\n\n\ndef install_legacy_compatibility() -> None:\n    """Compatibility no-op retained for historical imports."""\n\n\n__all__ = ("install_legacy_compatibility",)\n''',
)
replace_once(
    "velvet_bot/presentation/telegram/router.py",
    "from velvet_bot.presentation.telegram.compat import install_legacy_compatibility\n",
    "",
)
replace_once(
    "velvet_bot/presentation/telegram/router.py",
    "    install_legacy_compatibility()\n",
    "",
)

write(
    "tests/test_phase17_no_runtime_monkeypatches.py",
    '''from __future__ import annotations\n\nimport ast\nimport unittest\nfrom pathlib import Path\n\nimport velvet_bot.analytics_review as analytics_review\nimport velvet_bot.media_quality as media_quality\nfrom velvet_bot import runtime_log_hotfixes\nfrom velvet_bot.safe_analytics_edit import install_safe_analytics_edit\n\n\nROOT = Path(__file__).resolve().parents[1]\n\n\nclass RuntimeCompatibilityRemovalTests(unittest.TestCase):\n    def test_runtime_exports_are_canonical_functions(self) -> None:\n        self.assertIs(\n            runtime_log_hotfixes.set_manual_publication_type,\n            analytics_review.set_manual_publication_type,\n        )\n        self.assertIs(\n            runtime_log_hotfixes.decide_duplicate_candidate,\n            media_quality.decide_duplicate_candidate,\n        )\n        self.assertIs(\n            runtime_log_hotfixes.scan_media_target,\n            media_quality.scan_media_target,\n        )\n\n    def test_installers_are_noops(self) -> None:\n        self.assertIsNone(runtime_log_hotfixes.install_runtime_log_hotfixes())\n        self.assertIsNone(install_safe_analytics_edit())\n\n    def test_root_router_does_not_install_legacy_compatibility(self) -> None:\n        source = (\n            ROOT / "velvet_bot/presentation/telegram/router.py"\n        ).read_text(encoding="utf-8")\n        self.assertNotIn("install_legacy_compatibility", source)\n\n    def test_compatibility_modules_do_not_assign_foreign_functions(self) -> None:\n        for relative in (\n            "velvet_bot/runtime_log_hotfixes.py",\n            "velvet_bot/safe_analytics_edit.py",\n            "velvet_bot/presentation/telegram/compat.py",\n        ):\n            path = ROOT / relative\n            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))\n            assignments = [\n                node\n                for node in ast.walk(tree)\n                if isinstance(node, (ast.Assign, ast.AnnAssign))\n                and isinstance(getattr(node, "target", None), ast.Attribute)\n            ]\n            self.assertEqual([], assignments, relative)\n\n    def test_manual_classification_sql_is_explicitly_typed(self) -> None:\n        source = (ROOT / "velvet_bot/analytics_review.py").read_text(encoding="utf-8")\n        self.assertIn("post_type = $3::VARCHAR", source)\n        self.assertIn("publication_key = $2::VARCHAR", source)\n        self.assertIn("$3::VARCHAR = 'prompt'::VARCHAR", source)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
)

(ROOT / "scripts/_phase17_patch.py").unlink()
(ROOT / ".github/workflows/phase17-patch.yml").unlink()
