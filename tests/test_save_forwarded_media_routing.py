from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from velvet_bot.media import extract_media
from velvet_bot.presentation.telegram.routers.archive import pending_save, save


def _document_message(*, file_name: str, mime_type: str | None):
    return SimpleNamespace(
        photo=None,
        video=None,
        animation=None,
        document=SimpleNamespace(
            file_id="document-id",
            file_unique_id="document-unique",
            file_name=file_name,
            mime_type=mime_type,
            file_size=1024,
            thumbnail=None,
        ),
    )


class ForwardedMediaExtractionTests(unittest.TestCase):
    def test_png_with_generic_mime_is_supported(self) -> None:
        media = extract_media(
            _document_message(
                file_name="019e856a-b274-70ba-b909-e8112dd784bc.png",
                mime_type="application/octet-stream",
            )
        )

        self.assertIsNotNone(media)
        assert media is not None
        self.assertEqual(media.media_type, "document")
        self.assertEqual(media.mime_type, "image/png")
        self.assertTrue(media.storage_file_name.endswith(".png"))

    def test_png_without_mime_is_supported(self) -> None:
        media = extract_media(_document_message(file_name="result.PNG", mime_type=None))

        self.assertIsNotNone(media)
        assert media is not None
        self.assertEqual(media.mime_type, "image/png")

    def test_non_media_binary_document_is_rejected(self) -> None:
        media = extract_media(
            _document_message(
                file_name="notes.pdf",
                mime_type="application/octet-stream",
            )
        )

        self.assertIsNone(media)


class PendingSaveRoutingTests(unittest.TestCase):
    def test_priority_router_reuses_canonical_pending_handler(self) -> None:
        callbacks = [handler.callback for handler in pending_save.router.message.handlers]

        self.assertIn(save.handle_pending_save_upload, callbacks)

    def test_priority_router_precedes_reference_media_routers(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")

        pending_index = source.index("router.include_router(pending_save_router)")
        documents_index = source.index("router.include_router(reference_documents_router)")
        references_index = source.index("router.include_router(references_router)")

        self.assertLess(pending_index, documents_index)
        self.assertLess(pending_index, references_index)


if __name__ == "__main__":
    unittest.main()
