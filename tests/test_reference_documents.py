import unittest

from aiogram.types import Document

from velvet_bot.handlers.reference_albums import chunk_references
from velvet_bot.reference_media import (
    MAX_REFERENCE_DOCUMENT_BYTES,
    validate_reference_document,
)


class ReferenceDocumentValidationTests(unittest.TestCase):
    def test_png_document_is_accepted_by_mime_type(self) -> None:
        document = Document(
            file_id="file-id",
            file_unique_id="unique-id",
            file_name="reference.bin",
            mime_type="image/png",
        )
        self.assertIsNone(validate_reference_document(document))

    def test_image_extension_is_used_when_mime_type_is_generic(self) -> None:
        document = Document(
            file_id="file-id",
            file_unique_id="unique-id",
            file_name="reference.JPG",
            mime_type="application/octet-stream",
        )
        self.assertIsNone(validate_reference_document(document))

    def test_non_image_document_is_rejected(self) -> None:
        document = Document(
            file_id="file-id",
            file_unique_id="unique-id",
            file_name="reference.pdf",
            mime_type="application/pdf",
        )
        self.assertIsNotNone(validate_reference_document(document))

    def test_oversized_document_is_rejected(self) -> None:
        document = Document(
            file_id="file-id",
            file_unique_id="unique-id",
            file_name="reference.png",
            mime_type="image/png",
            file_size=MAX_REFERENCE_DOCUMENT_BYTES + 1,
        )
        self.assertIsNotNone(validate_reference_document(document))


class ReferenceAlbumBatchTests(unittest.TestCase):
    def test_two_references_stay_in_one_album(self) -> None:
        self.assertEqual([[1, 2]], chunk_references([1, 2]))

    def test_telegram_album_limit_is_respected(self) -> None:
        batches = chunk_references(list(range(12)))
        self.assertEqual([10, 2], [len(batch) for batch in batches])


if __name__ == "__main__":
    unittest.main()
