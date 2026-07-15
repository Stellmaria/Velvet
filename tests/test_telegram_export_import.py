import io
import json
import unittest
import zipfile

from velvet_bot.telegram_export_import import (
    flatten_export_text,
    infer_export_chat_id,
    load_export_payload,
    parse_export_records,
)


class TelegramExportImportTests(unittest.TestCase):
    def sample_payload(self):
        return {
            "name": "Vᴇʟᴠᴇᴛ Aɴᴀᴛᴏᴍʏ",
            "type": "public_channel",
            "id": 3802812639,
            "messages": [
                {
                    "id": 12,
                    "type": "message",
                    "date": "2026-06-01T22:09:23",
                    "date_unixtime": "1780340963",
                    "from": "Velvet",
                    "from_id": "channel3802812639",
                    "photo": "photos/1.jpg",
                    "media_spoiler": True,
                    "text": [
                        {"type": "bold", "text": "ВАЖНО:"},
                        "\nТекст\n",
                        {"type": "bold", "text": "СТРОГО:"},
                        "\nПравила #Каин",
                    ],
                    "reactions": [
                        {"type": "emoji", "emoji": "❤", "count": 4}
                    ],
                },
                {
                    "id": 13,
                    "type": "message",
                    "date": "2026-06-01T22:09:23",
                    "date_unixtime": "1780340963",
                    "from": "Velvet",
                    "from_id": "channel3802812639",
                    "photo": "photos/2.jpg",
                    "text": "",
                },
                {
                    "id": 14,
                    "type": "message",
                    "date": "2026-06-02T10:00:00",
                    "date_unixtime": "1780383600",
                    "from": "Velvet",
                    "from_id": "channel3802812639",
                    "text": "Обычный пост #новости",
                },
            ],
        }

    def test_flatten_export_text_preserves_entities(self) -> None:
        self.assertEqual(
            "ВАЖНО:\nТекст",
            flatten_export_text(
                [{"type": "bold", "text": "ВАЖНО:"}, "\nТекст"]
            ),
        )

    def test_public_channel_id_is_converted_to_bot_api_id(self) -> None:
        self.assertEqual(-1003802812639, infer_export_chat_id(self.sample_payload()))

    def test_media_album_becomes_one_publication(self) -> None:
        records = parse_export_records(self.sample_payload())
        self.assertEqual(3, len(records))
        self.assertEqual(records[0].publication_key, records[1].publication_key)
        self.assertNotEqual(records[1].publication_key, records[2].publication_key)
        self.assertTrue(records[0].has_spoiler)
        self.assertEqual(4, records[0].reactions_total)
        self.assertEqual("photo", records[0].media_type)

    def test_result_json_is_loaded_directly(self) -> None:
        raw = json.dumps(self.sample_payload(), ensure_ascii=False).encode("utf-8")
        loaded = load_export_payload(raw, "result.json")
        self.assertEqual("Vᴇʟᴠᴇᴛ Aɴᴀᴛᴏᴍʏ", loaded["name"])

    def test_result_json_is_loaded_from_zip_without_extracting_media(self) -> None:
        destination = io.BytesIO()
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr(
                "result.json",
                json.dumps(self.sample_payload(), ensure_ascii=False),
            )
            archive.writestr("photos/large-placeholder.jpg", b"not-read")
        loaded = load_export_payload(destination.getvalue(), "export.zip")
        self.assertEqual(3, len(loaded["messages"]))

    def test_invalid_export_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            load_export_payload(b"{}", "result.json")


if __name__ == "__main__":
    unittest.main()
