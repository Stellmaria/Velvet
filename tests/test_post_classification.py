import unittest

from velvet_bot.post_classification import classify_post


class PostClassificationTests(unittest.TestCase):
    def test_prompt_has_highest_priority(self) -> None:
        result = classify_post(
            "ВАЖНО:\nТекст\nСТРОГО:\nПравила",
            (("анонс", "анонс"),),
            is_prompt=True,
            media_type="photo",
        )
        self.assertEqual("prompt", result.post_type)
        self.assertGreaterEqual(result.confidence, 95)

    def test_prompt_structure_is_rediscovered_after_manual_override(self) -> None:
        result = classify_post(
            "ВАЖНО:\nСохранить внешность.\nСТРОГО:\nНе менять лицо.",
            (),
            is_prompt=False,
            media_type="photo",
        )
        self.assertEqual("prompt", result.post_type)
        self.assertGreaterEqual(result.confidence, 95)

    def test_giveaway_by_hashtag(self) -> None:
        result = classify_post(
            "Создайте работу и участвуйте",
            (("розыгрыш", "розыгрыш"),),
            is_prompt=False,
            media_type="photo",
        )
        self.assertEqual("giveaway", result.post_type)
        self.assertEqual(98, result.confidence)

    def test_collaboration_by_text(self) -> None:
        result = classify_post(
            "Совместная работа с другим каналом",
            (),
            is_prompt=False,
            media_type="photo",
        )
        self.assertEqual("collaboration", result.post_type)

    def test_media_falls_back_to_art(self) -> None:
        result = classify_post(
            "Новая работа",
            (),
            is_prompt=False,
            media_type="photo",
        )
        self.assertEqual("art", result.post_type)
        self.assertLess(result.confidence, 70)

    def test_plain_text_can_remain_unknown(self) -> None:
        result = classify_post(
            "Добрый вечер",
            (),
            is_prompt=False,
            media_type="text",
        )
        self.assertEqual("unknown", result.post_type)


if __name__ == "__main__":
    unittest.main()
