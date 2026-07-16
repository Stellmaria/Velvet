from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from velvet_bot.media_sets import (
    _MediaContext,
    _build_context_components,
    _drafts_from_contexts,
    _filename_family,
)
from velvet_bot.quality_ui import quality_callback


class MediaSetHeuristicTests(unittest.TestCase):
    def make_context(
        self,
        media_id: int,
        *,
        character: str,
        file_name: str,
        minutes: int = 0,
        universe: str = "original",
        prompt_url: str | None = None,
        phash: str = "0f0f0f0f0f0f0f0f",
    ) -> _MediaContext:
        return _MediaContext(
            media_id=media_id,
            telegram_file_id=f"file-{media_id}",
            media_type="photo",
            file_name=file_name,
            linked_at=datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
            + timedelta(minutes=minutes),
            characters=(character,),
            universes=(universe,),
            story_ids=(),
            prompt_post_url=prompt_url,
            width=1024,
            height=1536,
            phash=phash,
        )

    def test_filename_family_removes_character_and_generated_suffix(self) -> None:
        self.assertEqual(
            "wild west",
            _filename_family(
                "Wild_West_Ada__1234567890abcdef12345678.png",
                ("Ада", "Ada"),
            ),
        )

    def test_shared_prompt_builds_one_multi_item_candidate(self) -> None:
        prompt = "https://t.me/velvet/100"
        contexts = tuple(
            self.make_context(
                media_id,
                character=character,
                file_name=f"western_{character}.png",
                minutes=media_id,
                prompt_url=prompt,
            )
            for media_id, character in ((1, "Ada"), (2, "Eric"), (3, "Kael"))
        )
        drafts = _drafts_from_contexts(contexts)
        prompt_drafts = [draft for draft in drafts if draft.prompt_post_url == prompt]
        self.assertEqual(1, len(prompt_drafts))
        self.assertEqual((1, 2, 3), tuple(item[0] for item in prompt_drafts[0].items))
        self.assertEqual(100, prompt_drafts[0].score)

    def test_context_component_groups_different_characters_in_same_series(self) -> None:
        contexts = (
            self.make_context(
                1,
                character="Ada",
                file_name="wild-west-ada.png",
                minutes=0,
            ),
            self.make_context(
                2,
                character="Eric",
                file_name="wild-west-eric.png",
                minutes=4,
                phash="0f0f0f0f0f0f0f1f",
            ),
            self.make_context(
                3,
                character="Kael",
                file_name="wild-west-kael.png",
                minutes=8,
                phash="0f0f0f0f0f0f0f3f",
            ),
        )
        components = _build_context_components(contexts)
        self.assertEqual(1, len(components))
        self.assertEqual((1, 2, 3), tuple(item.media_id for item in components[0]))

    def test_context_component_does_not_cross_universes(self) -> None:
        contexts = (
            self.make_context(
                1,
                character="Ada",
                file_name="wild-west-ada.png",
                universe="original",
            ),
            self.make_context(
                2,
                character="Eric",
                file_name="wild-west-eric.png",
                universe="kr",
                minutes=2,
            ),
        )
        self.assertEqual((), _build_context_components(contexts))

    def test_set_callbacks_stay_inside_telegram_limit(self) -> None:
        values = (
            quality_callback(
                "settoggle",
                page=9223372036854775807,
                item_id=9223372036854775807,
            ),
            quality_callback(
                "dupdelask",
                section="second",
                page=999999,
                item_id=9223372036854775807,
            ),
        )
        for value in values:
            self.assertLessEqual(len(value.encode("utf-8")), 64, value)


if __name__ == "__main__":
    unittest.main()
