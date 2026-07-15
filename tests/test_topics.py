import unittest

from velvet_bot.topics import parse_private_topic_link, split_character_and_topic


class TopicLinkTests(unittest.TestCase):
    def test_private_topic_link_is_converted_to_bot_chat_id(self) -> None:
        topic = parse_private_topic_link(
            "https://t.me/c/3951213065/1398"
        )

        self.assertEqual(-1003951213065, topic.chat_id)
        self.assertEqual(1398, topic.thread_id)
        self.assertEqual(
            "https://t.me/c/3951213065/1398",
            topic.url,
        )

    def test_create_arguments_support_multiword_character_name(self) -> None:
        name, topic = split_character_and_topic(
            "Темный Аид https://t.me/c/3951213065/1398"
        )

        self.assertEqual("Темный Аид", name)
        self.assertIsNotNone(topic)

    def test_create_arguments_can_omit_topic_for_legacy_profiles(self) -> None:
        name, topic = split_character_and_topic("Темный Аид")

        self.assertEqual("Темный Аид", name)
        self.assertIsNone(topic)

    def test_public_or_message_link_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_private_topic_link("https://t.me/public_chat/1398")
