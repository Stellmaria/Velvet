from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PERSONAL_DEFAULTS = (
    "va_stellmaria",
    "8179531132",
    "5367533184",
    "1003802812639",
)
SECRET_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def tracked_files() -> tuple[Path, ...]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return tuple(
        ROOT / item.decode("utf-8")
        for item in completed.stdout.split(b"\0")
        if item
    )


class PublicRepositorySafetyTests(unittest.TestCase):
    def test_runtime_secrets_and_data_are_not_tracked(self) -> None:
        tracked = {path.relative_to(ROOT).as_posix() for path in tracked_files()}
        forbidden = {".env", "result.json", "database.dump", "velvet.db"}
        self.assertFalse(forbidden & tracked)
        for value in tracked:
            self.assertFalse(value.startswith(("backups/", "logs/", "runtime/", "data/")))
            self.assertFalse(value.endswith((".dump", ".db", ".db-wal", ".db-shm")))

    def test_active_configuration_contains_no_personal_defaults(self) -> None:
        paths = [
            ROOT / ".env.example",
            ROOT / "README.md",
            *sorted((ROOT / "velvet_bot").rglob("*.py")),
            *sorted((ROOT / "velvet_supervisor").rglob("*.py")),
            *sorted((ROOT / "scripts").glob("*.py")),
            ROOT / "docs/telegram_analytics_import.md",
            ROOT / "docs/PUBLICATION_WORKFLOW.md",
        ]
        for path in paths:
            source = path.read_text(encoding="utf-8")
            for value in PERSONAL_DEFAULTS:
                with self.subTest(path=path.relative_to(ROOT), value=value):
                    self.assertNotIn(value, source)

    def test_operational_sources_contain_no_obvious_credentials(self) -> None:
        for path in tracked_files():
            relative = path.relative_to(ROOT)
            if relative.parts[0] in {"tests", "migrations", "tools"}:
                continue
            if relative.parts[:2] == ("docs", "worklog"):
                continue
            if path.suffix.lower() not in {
                ".py", ".md", ".yml", ".yaml", ".toml", ".json", ".env", ""
            }:
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for pattern in SECRET_PATTERNS:
                with self.subTest(path=relative, pattern=pattern.pattern):
                    self.assertIsNone(pattern.search(source))

    def test_example_requires_explicit_telegram_identities(self) -> None:
        values = {}
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
        self.assertEqual("insert_owner_telegram_user_id", values["ALLOWED_USER_IDS"])
        self.assertEqual("", values["ALLOWED_USERNAMES"])
        self.assertEqual("", values["MODERATOR_USER_IDS"])
        self.assertEqual("", values["LOG_CHAT_ID"])
        self.assertEqual("", values["ANALYTICS_CHANNEL_IDS"])


if __name__ == "__main__":
    unittest.main()
