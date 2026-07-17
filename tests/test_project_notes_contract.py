from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_project_notes.py"
SPEC = importlib.util.spec_from_file_location("check_project_notes", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Не удалось загрузить scripts/check_project_notes.py")
notes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notes)


class ProjectNotesContractTests(unittest.TestCase):
    def test_repository_notes_are_complete(self) -> None:
        self.assertEqual([], notes.validate_repository(require_final=True))

    def test_meaningful_change_requires_worklog_entry(self) -> None:
        errors = notes.validate_changed_files(("velvet_bot/example.py",))
        self.assertEqual(1, len(errors))
        self.assertIn("docs/worklog", errors[0])

    def test_worklog_requires_both_start_and_finish_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "2026-07-17-incomplete.md"
            path.write_text(
                "# Сессия\n\n"
                "- Дата: 2026-07-17\n"
                "- ID: `2026-07-17-incomplete`\n"
                "- Линия/фаза: test\n"
                "- Статус: завершено\n"
                "- Ветка: test\n"
                "- Базовый commit: `abc`\n\n"
                "## Перед началом\n\n"
                "### Цель\n",
                encoding="utf-8",
            )
            errors = notes.validate_worklog(path, require_final=True)
        self.assertTrue(any("После завершения" in error for error in errors))

    def test_in_progress_status_is_rejected_before_merge(self) -> None:
        template = (ROOT / "docs" / "worklog" / "README.md").read_text(encoding="utf-8")
        sample = template.split("```markdown", 1)[1].split("```", 1)[0].strip()
        sample = sample.replace("YYYY-MM-DD-slug", "2026-07-17-sample")
        sample = sample.replace("YYYY-MM-DD", "2026-07-17")
        sample = sample.replace("- Статус: в работе", "- Статус: в работе")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "2026-07-17-sample.md"
            path.write_text(sample, encoding="utf-8")
            errors = notes.validate_worklog(path, require_final=True)
        self.assertTrue(any("статус" in error.casefold() for error in errors))


if __name__ == "__main__":
    unittest.main()
