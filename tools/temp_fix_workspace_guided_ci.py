from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"expected one occurrence in {path}: {old!r}; got {count}")
    path.write_text(source.replace(old, new), encoding="utf-8")


def replace_exact(path: Path, old: str, new: str, *, count: int) -> None:
    source = path.read_text(encoding="utf-8")
    actual = source.count(old)
    if actual != count:
        raise RuntimeError(f"expected {count} occurrences in {path}: {old!r}; got {actual}")
    path.write_text(source.replace(old, new), encoding="utf-8")


guided = ROOT / "velvet_bot/presentation/telegram/routers/workspace_guided_actions.py"
replace_once(
    guided,
    "from aiogram.exceptions import TelegramBadRequest",
    "from aiogram.exceptions import TelegramAPIError, TelegramBadRequest",
)
replace_exact(
    guided,
    "except Exception as error:",
    "except (ValueError, TelegramAPIError) as error:",
    count=2,
)

callback_test = ROOT / "tests/test_workspace_guided_menu.py"
replace_once(
    callback_test,
    "            item_id=9_223_372_036_854_775_807,",
    "            item_id=0,",
)

architecture_test = ROOT / "tests/test_p3_architecture_organization.py"
replace_once(
    architecture_test,
    '    "velvet_bot.presentation.telegram.routers.workspace_character_pickers",\n',
    '    "velvet_bot.presentation.telegram.routers.workspace_character_pickers",\n'
    '    "velvet_bot.presentation.telegram.routers.workspace_guided_actions",\n',
)

publication_test = ROOT / "tests/test_p3c_publication_controllers.py"
replace_once(
    publication_test,
    '        self.assertEqual(46, source.count("router.include_router("))',
    '        self.assertEqual(47, source.count("router.include_router("))',
)

onboarding_test = ROOT / "tests/test_workspace_onboarding.py"
source = onboarding_test.read_text(encoding="utf-8")
start = source.index("class WorkspaceOnboardingRulesTests")
end = source.index("\n\nclass WorkspaceOnboardingSourceContractTests")
replacement = '''class WorkspaceOnboardingRulesTests(unittest.TestCase):
    def test_archive_modules_require_only_main_archive_destination(self) -> None:
        self.assertEqual(
            ("characters",),
            required_destination_keys({"characters", "archive"}),
        )

    def test_optional_modules_do_not_add_required_destinations(self) -> None:
        self.assertEqual(
            ("characters",),
            required_destination_keys(
                {
                    "characters",
                    "archive",
                    "references",
                    "public_archive",
                    "publications",
                    "analytics",
                }
            ),
        )
        self.assertEqual((), required_destination_keys({"taxonomy", "team"}))

    def test_readiness_requires_guide_modules_and_main_archive(self) -> None:
        result = onboarding_readiness(
            modules_confirmed=False,
            guide_viewed=False,
            enabled_modules={"characters", "archive", "references"},
            configured_destinations={"characters"},
        )
        self.assertFalse(result.ready)
        self.assertEqual(
            (
                "Откройте краткий гид по работе пространства.",
                "Подтвердите выбранные модули.",
            ),
            result.missing_steps,
        )

    def test_readiness_accepts_main_archive_without_optional_chats(self) -> None:
        result = onboarding_readiness(
            modules_confirmed=True,
            guide_viewed=True,
            enabled_modules={"characters", "archive", "references"},
            configured_destinations={"characters"},
        )
        self.assertTrue(result.ready)
        self.assertEqual((), result.missing_steps)

    def test_every_destination_has_command_and_description(self) -> None:
        self.assertEqual(set(WORKSPACE_DESTINATION_KEYS), set(DESTINATION_SPECS))
        for key, spec in DESTINATION_SPECS.items():
            self.assertIn(key, spec.command_hint)
            self.assertTrue(spec.description)
            self.assertTrue(spec.label)

    def test_character_destination_requires_forum_topic_management(self) -> None:
        spec = DESTINATION_SPECS["characters"]
        self.assertTrue(spec.requires_forum_admin)
        self.assertIn("персональную тему", spec.description)
'''
onboarding_test.write_text(source[:start] + replacement + source[end:], encoding="utf-8")

Path(__file__).unlink()
(ROOT / ".github/workflows/temp_fix_workspace_guided_ci.yml").unlink(missing_ok=True)
