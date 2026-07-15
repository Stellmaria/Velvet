import unittest
from datetime import UTC, datetime
from types import SimpleNamespace

from velvet_bot.channel_analytics import (
    analyze_prompt_text,
    compact_identity,
    extract_hashtags,
    extract_links,
    parse_channel_post,
)


class ChannelAnalyticsTests(unittest.TestCase):
    def test_hashtags_are_unique_and_palette_colors_are_ignored(self) -> None:
        hashtags = extract_hashtags(
            "#Аид #аид #DemianRaiven #МЖ #A17C6B #FFFFFF"
        )
        self.assertEqual(
            (
                ("Аид", "аид"),
                ("DemianRaiven", "demianraiven"),
                ("МЖ", "мж"),
            ),
            hashtags,
        )

    def test_compact_identity_matches_spaced_character_name(self) -> None:
        self.assertEqual(
            compact_identity("Demian Raiven"),
            compact_identity("Demian_Raiven"),
        )

    def test_prompt_detector_recognizes_velvet_structure(self) -> None:
        text = (
            "ВАЖНО:\nВ кадре взрослый персонаж 25+.\n\n"
            "СТРОГО:\nИспользуй референс для внешности.\n\n"
            "Композиция и поза: портрет 9:16.\n"
            "📷 85 mm | f/2.0 | shallow DOF\n"
            "Negative prompt: plastic skin.\n"
            "Палитра: #1B1718 #6D4C41 #C8A48B"
        )
        signals = analyze_prompt_text(text)
        self.assertTrue(signals.is_prompt)
        self.assertTrue(signals.has_important)
        self.assertTrue(signals.has_strict)
        self.assertTrue(signals.has_negative)
        self.assertTrue(signals.has_technical)
        self.assertTrue(signals.has_palette)

    def test_links_detect_telegram_domain(self) -> None:
        links = extract_links(
            "Промт: https://t.me/velvet/123 и сайт https://example.com/page."
        )
        self.assertIn(("https://t.me/velvet/123", "t.me", True), links)
        self.assertIn(("https://example.com/page", "example.com", False), links)

    def test_album_uses_single_publication_key(self) -> None:
        message = SimpleNamespace(
            text=None,
            caption="#Аид\nВАЖНО:\nТекст\nСТРОГО:\nПравила",
            media_group_id="album-42",
            message_id=101,
            date=datetime(2026, 7, 16, 12, 0, tzinfo=UTC),
            edit_date=None,
            author_signature="Velvet",
            views=50,
            forward_count=2,
            has_media_spoiler=True,
            photo=[object()],
            chat=SimpleNamespace(
                id=-1003802812639,
                title="Velvet Anatomy",
                username="velvet_anatomy",
            ),
        )
        parsed = parse_channel_post(message)
        self.assertEqual("album:album-42", parsed.publication_key)
        self.assertEqual("photo", parsed.media_type)
        self.assertTrue(parsed.has_spoiler)
        self.assertEqual("https://t.me/velvet_anatomy/101", parsed.message_url)
        self.assertEqual((("Аид", "аид"),), parsed.hashtags)


if __name__ == "__main__":
    unittest.main()
