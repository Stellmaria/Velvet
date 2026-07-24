from pathlib import Path

path = Path("tests/test_p2_stability_inventory.py")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one P2 test block, found {count}: {old[:80]!r}")
    text = text.replace(old, new, 1)


replace_once(
    """from velvet_bot.presentation.telegram.routers.stories import multi_story_kr as multi_story
""",
    """from velvet_bot.presentation.telegram.routers import workspace_guided_actions
from velvet_bot.presentation.telegram.routers import workspace_reference_buttons
from velvet_bot.presentation.telegram.routers.stories import multi_story_kr as multi_story
""",
)
replace_once(
    """    def test_phase18_plan_is_not_stale(self) -> None:
""",
    """    def test_workspace_callbacks_ack_before_slow_operations(self) -> None:
        quick_source = inspect.getsource(
            workspace_guided_actions.handle_workspace_quick_entry
        )
        self.assertLess(
            quick_source.index(\"await callback.answer()\"),
            quick_source.index(\"await state.clear()\"),
        )
        self.assertLess(
            quick_source.index(\"await callback.answer()\"),
            quick_source.index(\"await _render_quick(\"),
        )

        taxonomy_source = inspect.getsource(
            workspace_guided_actions.handle_guided_taxonomy_entry
        )
        for operation in (
            \"await _start_category(\",
            \"await _start_universe(\",
            \"await _start_story(\",
        ):
            self.assertLess(
                taxonomy_source.index(\"await callback.answer()\"),
                taxonomy_source.index(operation),
            )

        reference_source = inspect.getsource(
            workspace_reference_buttons.handle_reference_manage
        )
        self.assertLess(
            reference_source.index(\"await callback.answer()\"),
            reference_source.index(\"page = await get_reference_page(\"),
        )
        self.assertLess(
            reference_source.index(\"await callback.answer()\"),
            reference_source.index(\"rows = await _load_reference_characters(\"),
        )

    def test_phase18_plan_is_not_stale(self) -> None:
""",
)

path.write_text(text, encoding="utf-8")
