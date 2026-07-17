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
    "velvet_bot/handlers/publication_center.py",
    '''from velvet_bot.database import Database\nfrom velvet_bot.post_classification import POST_TYPE_LABELS\nfrom velvet_bot.publication_worker import publish_publication_draft\nfrom velvet_bot.publication_workflow import (\n    PublicationDraft,\n    cancel_publication,\n    capture_publication_inbox,\n    create_draft_from_message,\n    get_publication_draft,\n    list_publication_drafts,\n    retry_publication,\n    schedule_publication,\n    set_publication_spoiler,\n    update_publication_text,\n    validate_publication_draft,\n)\n''',
    '''from velvet_bot.app.publication import build_publication_service\nfrom velvet_bot.application.publication_actions import build_publication_actions\nfrom velvet_bot.database import Database\nfrom velvet_bot.domains.publication import PublicationDraft\nfrom velvet_bot.post_classification import POST_TYPE_LABELS\nfrom velvet_bot.publication_drafts import capture_publication_inbox\nfrom velvet_bot.services.telegram_publications import create_publication_draft\n''',
)
replace_once(
    "velvet_bot/handlers/publication_center.py",
    '''    draft = await get_publication_draft(\n        database,\n        draft_id,\n        owner_id=callback.from_user.id,\n    )\n''',
    '''    draft = await build_publication_actions(database).get_draft(\n        draft_id,\n        owner_id=callback.from_user.id,\n    )\n''',
)
replace_once(
    "velvet_bot/handlers/publication_center.py",
    '''    result = await list_publication_drafts(\n        database,\n        owner_id=callback.from_user.id,\n        statuses=statuses,\n        page=page,\n    )\n''',
    '''    result = await build_publication_actions(database).list_drafts(\n        owner_id=callback.from_user.id,\n        statuses=statuses,\n        page=page,\n    )\n''',
)
replace_once(
    "velvet_bot/handlers/publication_center.py",
    '''    target_chat_id = sorted(analytics_channel_ids)[0]\n    draft = await create_draft_from_message(\n        database,\n        source,\n        owner_id=message.from_user.id,\n        target_chat_id=target_chat_id,\n    )\n''',
    '''    draft = await create_publication_draft(\n        database,\n        source,\n        analytics_channel_ids=analytics_channel_ids,\n        owner_id=message.from_user.id,\n    )\n''',
)
replace_once(
    "velvet_bot/handlers/publication_center.py",
    '''    draft = await get_publication_draft(\n        database,\n        callback_data.draft_id,\n        owner_id=callback.from_user.id,\n    )\n''',
    '''    actions = build_publication_actions(database)\n    draft = await actions.get_draft(\n        callback_data.draft_id,\n        owner_id=callback.from_user.id,\n    )\n''',
)
replace_once(
    "velvet_bot/handlers/publication_center.py",
    '''        await validate_publication_draft(\n            database,\n            draft.id,\n            owner_id=callback.from_user.id,\n        )\n''',
    '''        await actions.recheck(\n            draft.id,\n            owner_id=callback.from_user.id,\n        )\n''',
)
replace_once(
    "velvet_bot/handlers/publication_center.py",
    '''        await set_publication_spoiler(\n            database,\n            draft.id,\n            owner_id=callback.from_user.id,\n            enabled=not draft.has_spoiler,\n        )\n''',
    '''        await actions.set_spoiler(\n            draft.id,\n            owner_id=callback.from_user.id,\n            enabled=not draft.has_spoiler,\n        )\n''',
)
replace_once(
    "velvet_bot/handlers/publication_center.py",
    '''            result = await publish_publication_draft(\n                bot,\n                database,\n                draft.id,\n                owner_id=callback.from_user.id,\n                actor_id=callback.from_user.id,\n            )\n''',
    '''            result = await build_publication_service(bot, database).publish(\n                draft.id,\n                owner_id=callback.from_user.id,\n                actor_id=callback.from_user.id,\n            )\n''',
)
replace_once(
    "velvet_bot/handlers/publication_center.py",
    '''        await cancel_publication(database, draft.id, owner_id=callback.from_user.id)\n''',
    '''        await actions.cancel(draft.id, owner_id=callback.from_user.id)\n''',
)
replace_once(
    "velvet_bot/handlers/publication_center.py",
    '''        await retry_publication(database, draft.id, owner_id=callback.from_user.id)\n''',
    '''        await actions.retry(draft.id, owner_id=callback.from_user.id)\n''',
)
replace_once(
    "velvet_bot/handlers/publication_center.py",
    '''        draft = await schedule_publication(\n            database,\n            draft_id,\n            owner_id=message.from_user.id,\n            scheduled_at=local_value.astimezone(timezone.utc),\n        )\n''',
    '''        draft = await build_publication_actions(database).schedule(\n            draft_id,\n            owner_id=message.from_user.id,\n            scheduled_at=local_value.astimezone(timezone.utc),\n        )\n''',
)
replace_once(
    "velvet_bot/handlers/publication_center.py",
    '''        draft = await update_publication_text(\n            database,\n            draft_id,\n            owner_id=message.from_user.id,\n            text=message.text or message.caption or "",\n        )\n''',
    '''        draft = await build_publication_actions(database).update_text(\n            draft_id,\n            owner_id=message.from_user.id,\n            text=message.text or message.caption or "",\n        )\n''',
)

write(
    "velvet_bot/application/publication_actions.py",
    '''from __future__ import annotations\n\nfrom datetime import datetime\n\nfrom velvet_bot.app.publication_drafts import build_publication_draft_service\nfrom velvet_bot.database import Database\nfrom velvet_bot.domains.publication import (\n    PublicationDraft,\n    PublicationDraftPage,\n    PublicationRepository,\n)\nfrom velvet_bot.domains.publication.draft_service import PublicationDraftService\nfrom velvet_bot.domains.publication.validation_service import PublicationValidationService\nfrom velvet_bot.publication_validation import build_publication_validation_service\n\n\nclass PublicationActions:\n    """Transport-neutral actions used by publication UI adapters."""\n\n    def __init__(\n        self,\n        *,\n        drafts: PublicationRepository,\n        commands: PublicationDraftService,\n        validation: PublicationValidationService,\n    ) -> None:\n        self._drafts = drafts\n        self._commands = commands\n        self._validation = validation\n\n    async def get_draft(\n        self,\n        draft_id: int,\n        *,\n        owner_id: int | None = None,\n    ) -> PublicationDraft | None:\n        return await self._drafts.get_draft(draft_id, owner_id=owner_id)\n\n    async def list_drafts(\n        self,\n        *,\n        owner_id: int,\n        statuses: tuple[str, ...],\n        page: int = 0,\n        page_size: int = 6,\n    ) -> PublicationDraftPage:\n        return await self._drafts.list_drafts(\n            owner_id=owner_id,\n            statuses=statuses,\n            page=page,\n            page_size=page_size,\n        )\n\n    async def recheck(self, draft_id: int, *, owner_id: int) -> PublicationDraft:\n        return await self._validation.validate(draft_id, owner_id=owner_id)\n\n    async def set_spoiler(\n        self,\n        draft_id: int,\n        *,\n        owner_id: int,\n        enabled: bool,\n    ) -> PublicationDraft:\n        return await self._commands.set_spoiler(\n            draft_id,\n            owner_id=owner_id,\n            enabled=enabled,\n        )\n\n    async def update_text(\n        self,\n        draft_id: int,\n        *,\n        owner_id: int,\n        text: str,\n    ) -> PublicationDraft:\n        return await self._commands.update_text(\n            draft_id,\n            owner_id=owner_id,\n            text=text,\n        )\n\n    async def schedule(\n        self,\n        draft_id: int,\n        *,\n        owner_id: int,\n        scheduled_at: datetime,\n    ) -> PublicationDraft:\n        return await self._commands.schedule(\n            draft_id,\n            owner_id=owner_id,\n            scheduled_at=scheduled_at,\n        )\n\n    async def cancel(self, draft_id: int, *, owner_id: int) -> PublicationDraft:\n        return await self._commands.cancel(draft_id, owner_id=owner_id)\n\n    async def retry(self, draft_id: int, *, owner_id: int) -> PublicationDraft:\n        return await self._commands.retry(draft_id, owner_id=owner_id)\n\n\ndef build_publication_actions(database: Database) -> PublicationActions:\n    return PublicationActions(\n        drafts=PublicationRepository(database),\n        commands=build_publication_draft_service(database),\n        validation=build_publication_validation_service(database),\n    )\n\n\n__all__ = ("PublicationActions", "build_publication_actions")\n''',
)
write(
    "tests/test_phase13_publication_actions.py",
    '''from __future__ import annotations\n\nimport unittest\nfrom datetime import datetime, timezone\nfrom pathlib import Path\nfrom types import SimpleNamespace\nfrom unittest.mock import AsyncMock\n\nfrom velvet_bot.application.publication_actions import PublicationActions\n\n\nROOT = Path(__file__).resolve().parents[1]\n\n\nclass PublicationActionsTests(unittest.IsolatedAsyncioTestCase):\n    def setUp(self) -> None:\n        self.drafts = SimpleNamespace(\n            get_draft=AsyncMock(return_value="draft"),\n            list_drafts=AsyncMock(return_value="page"),\n        )\n        self.commands = SimpleNamespace(\n            set_spoiler=AsyncMock(return_value="spoiler"),\n            update_text=AsyncMock(return_value="text"),\n            schedule=AsyncMock(return_value="scheduled"),\n            cancel=AsyncMock(return_value="cancelled"),\n            retry=AsyncMock(return_value="retry"),\n        )\n        self.validation = SimpleNamespace(validate=AsyncMock(return_value="checked"))\n        self.actions = PublicationActions(\n            drafts=self.drafts,\n            commands=self.commands,\n            validation=self.validation,\n        )\n\n    async def test_reads_are_delegated(self) -> None:\n        self.assertEqual(\n            await self.actions.get_draft(12, owner_id=5),\n            "draft",\n        )\n        self.assertEqual(\n            await self.actions.list_drafts(\n                owner_id=5,\n                statuses=("draft", "checked"),\n                page=2,\n            ),\n            "page",\n        )\n        self.drafts.get_draft.assert_awaited_once_with(12, owner_id=5)\n        self.drafts.list_drafts.assert_awaited_once_with(\n            owner_id=5,\n            statuses=("draft", "checked"),\n            page=2,\n            page_size=6,\n        )\n\n    async def test_commands_are_delegated(self) -> None:\n        when = datetime(2026, 7, 18, 20, 30, tzinfo=timezone.utc)\n        self.assertEqual(await self.actions.recheck(1, owner_id=5), "checked")\n        self.assertEqual(\n            await self.actions.set_spoiler(1, owner_id=5, enabled=True),\n            "spoiler",\n        )\n        self.assertEqual(\n            await self.actions.update_text(1, owner_id=5, text="new"),\n            "text",\n        )\n        self.assertEqual(\n            await self.actions.schedule(1, owner_id=5, scheduled_at=when),\n            "scheduled",\n        )\n        self.assertEqual(await self.actions.cancel(1, owner_id=5), "cancelled")\n        self.assertEqual(await self.actions.retry(1, owner_id=5), "retry")\n\n        self.validation.validate.assert_awaited_once_with(1, owner_id=5)\n        self.commands.set_spoiler.assert_awaited_once_with(\n            1, owner_id=5, enabled=True\n        )\n        self.commands.update_text.assert_awaited_once_with(\n            1, owner_id=5, text="new"\n        )\n        self.commands.schedule.assert_awaited_once_with(\n            1, owner_id=5, scheduled_at=when\n        )\n        self.commands.cancel.assert_awaited_once_with(1, owner_id=5)\n        self.commands.retry.assert_awaited_once_with(1, owner_id=5)\n\n    def test_publication_handler_uses_application_actions(self) -> None:\n        source = (ROOT / "velvet_bot/handlers/publication_center.py").read_text(\n            encoding="utf-8"\n        )\n        application_source = (\n            ROOT / "velvet_bot/application/publication_actions.py"\n        ).read_text(encoding="utf-8")\n        self.assertIn("build_publication_actions", source)\n        self.assertNotIn("from velvet_bot.publication_workflow", source)\n        self.assertNotIn("from velvet_bot.publication_worker", source)\n        self.assertNotIn("aiogram", application_source)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
)

(ROOT / "scripts/_phase13_patch.py").unlink()
(ROOT / ".github/workflows/phase13-patch.yml").unlink()
