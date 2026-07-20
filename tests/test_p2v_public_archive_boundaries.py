from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.presentation.telegram.routers.public_archive.media_display as module
from velvet_bot.domains.public_archive import PublicDownloadSource


class FakeCallback:
    def __init__(self, *, user_id: int = 17) -> None:
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(chat=SimpleNamespace(id=user_id))
        self.answers: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args, **kwargs) -> None:
        self.answers.append((args, kwargs))


class PublicArchiveBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_manager_access = module.has_public_manager_access
        self.original_member_access = module._member_access
        self.original_get_page = module.get_archive_page
        self.original_resolve = module.resolve_public_download_source
        self.original_send = module._send_as_document
        self.original_record = module.record_public_media_download

        module.has_public_manager_access = lambda user, policy: False
        self.media = SimpleNamespace(
            id=11,
            media_type="document",
            display_file_name="image.png",
            requires_adult_channel=False,
        )
        self.page = SimpleNamespace(
            media=self.media,
            character=SimpleNamespace(id=7),
            offset=0,
        )

        async def load_page(*args, **kwargs):
            return self.page

        module.get_archive_page = load_page
        self.data = SimpleNamespace(
            action="download",
            character_id=7,
            offset=0,
            media_id=11,
        )

    def tearDown(self) -> None:
        module.has_public_manager_access = self.original_manager_access
        module._member_access = self.original_member_access
        module.get_archive_page = self.original_get_page
        module.resolve_public_download_source = self.original_resolve
        module._send_as_document = self.original_send
        module.record_public_media_download = self.original_record

    async def _run(self, callback: FakeCallback | None = None) -> FakeCallback:
        callback = callback or FakeCallback()
        await module.handle_public_download(
            callback,
            self.data,
            object(),
            object(),
            object(),
            -1003951213065,
        )
        return callback

    async def test_nonmember_without_approved_watermark_is_denied(self) -> None:
        async def member_access(*args, **kwargs):
            return False

        async def resolve(*args, **kwargs):
            return None

        module._member_access = member_access
        module.resolve_public_download_source = resolve
        callback = await self._run()

        self.assertEqual(len(callback.answers), 1)
        self.assertIn("watermark", callback.answers[0][0][0])
        self.assertTrue(callback.answers[0][1]["show_alert"])

    async def test_member_receives_original_and_download_is_recorded(self) -> None:
        events: list[tuple[str, object]] = []

        async def member_access(*args, **kwargs):
            return True

        async def resolve(*args, **kwargs):
            self.assertTrue(kwargs["member_access"])
            return PublicDownloadSource("original-file", "original")

        async def send(*args, **kwargs):
            events.append(("send", kwargs["telegram_file_id"]))

        async def record(*args, **kwargs):
            events.append(("record", kwargs["variant"]))

        module._member_access = member_access
        module.resolve_public_download_source = resolve
        module._send_as_document = send
        module.record_public_media_download = record

        callback = await self._run()
        self.assertEqual(events, [("send", "original-file"), ("record", "original")])
        self.assertEqual(callback.answers[0][0][0], "Файл отправлен в личный чат.")

    async def test_approved_watermark_is_sent_to_nonmember(self) -> None:
        events: list[str] = []

        async def member_access(*args, **kwargs):
            return False

        async def resolve(*args, **kwargs):
            return PublicDownloadSource("watermarked-file", "watermarked")

        async def send(*args, **kwargs):
            events.append(kwargs["telegram_file_id"])

        async def record(*args, **kwargs):
            events.append(kwargs["variant"])

        module._member_access = member_access
        module.resolve_public_download_source = resolve
        module._send_as_document = send
        module.record_public_media_download = record

        await self._run()
        self.assertEqual(events, ["watermarked-file", "watermarked"])

    async def test_download_failure_is_answered(self) -> None:
        async def member_access(*args, **kwargs):
            return True

        async def resolve(*args, **kwargs):
            return PublicDownloadSource("original-file", "original")

        async def fail_send(*args, **kwargs):
            raise RuntimeError("download failed")

        module._member_access = member_access
        module.resolve_public_download_source = resolve
        module._send_as_document = fail_send

        callback = await self._run()
        self.assertIn("Не удалось", callback.answers[0][0][0])
        self.assertTrue(callback.answers[0][1]["show_alert"])

    async def test_download_cancellation_is_not_swallowed(self) -> None:
        async def member_access(*args, **kwargs):
            return True

        async def resolve(*args, **kwargs):
            return PublicDownloadSource("original-file", "original")

        async def cancel_send(*args, **kwargs):
            raise asyncio.CancelledError

        module._member_access = member_access
        module.resolve_public_download_source = resolve
        module._send_as_document = cancel_send

        with self.assertRaises(asyncio.CancelledError):
            await self._run()


if __name__ == "__main__":
    unittest.main()
