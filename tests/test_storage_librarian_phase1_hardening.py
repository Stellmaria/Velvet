from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from velvet_bot.domains.telegram_storage.librarian_models import (
    HermesRunResult,
    LibrarianAnalysis,
    LibrarianJob,
    StorageLibrarianSettings,
)
from velvet_bot.domains.telegram_storage.librarian_repository import (
    StorageLibrarianRepository,
)

ROOT = Path(__file__).resolve().parents[1]

# Final merge-gate regression coverage on the current main baseline.


class _Transaction:
    async def __aenter__(self) -> "_Transaction":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def transaction(self) -> _Transaction:
        return _Transaction()

    async def execute(self, query: str, *args: object) -> str:
        self.calls.append((query, args))
        return "UPDATE 1"


class _Acquire:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _Connection:
        return self.connection

    async def __aexit__(self, *args: object) -> None:
        return None


class _Database:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def acquire(self) -> _Acquire:
        return _Acquire(self.connection)


def _settings() -> StorageLibrarianSettings:
    with patch.dict("os.environ", {}, clear=True):
        return StorageLibrarianSettings.from_env()


class StorageLibrarianRepositoryHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_persists_actual_ollama_analyzer(self) -> None:
        connection = _Connection()
        repository = StorageLibrarianRepository(_Database(connection))  # type: ignore[arg-type]
        analysis = LibrarianAnalysis(
            summary="Система исправна.",
            tags=("diagnostics",),
            entities=(),
            action_items=(),
            sensitivity="normal",
            confidence=95,
            raw={"summary": "Система исправна."},
        )
        await repository.complete(
            job=LibrarianJob(1, 7, 1, 3),
            settings=_settings(),
            analysis=analysis,
            source_excerpt="status=ok",
            run=HermesRunResult(
                "ollama-storage-safe",
                "{}",
                {},
                analyzer="ollama",
            ),
        )

        insert_query, insert_args = connection.calls[0]
        self.assertIn("$2::TEXT", insert_query)
        self.assertEqual("ollama", insert_args[1])
        self.assertEqual("velvet-librarian:qwen3-4b-text:v4", insert_args[2])

    async def test_terminal_validation_failure_is_not_requeued(self) -> None:
        connection = _Connection()
        repository = StorageLibrarianRepository(_Database(connection))  # type: ignore[arg-type]
        terminal = await repository.fail(
            LibrarianJob(1, 7, 1, 3),
            RuntimeError("schema mismatch"),
            terminal=True,
        )
        self.assertTrue(terminal)
        self.assertEqual("failed", connection.calls[0][1][1])

    async def test_retryable_transport_failure_is_requeued(self) -> None:
        connection = _Connection()
        repository = StorageLibrarianRepository(_Database(connection))  # type: ignore[arg-type]
        terminal = await repository.fail(
            LibrarianJob(1, 7, 1, 3),
            RuntimeError("network timeout"),
        )
        self.assertFalse(terminal)
        self.assertEqual("queued", connection.calls[0][1][1])


class StorageLibrarianDeployHardeningTests(unittest.TestCase):
    def test_only_one_ollama_model_can_stay_loaded(self) -> None:
        compose = (ROOT / "deploy/hermes-librarian/compose.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn('OLLAMA_MAX_LOADED_MODELS: "1"', compose)
        self.assertNotIn('OLLAMA_MAX_LOADED_MODELS: "2"', compose)

    def test_installer_smokes_actual_bot_to_ollama_path(self) -> None:
        installer = (ROOT / "deploy/hermes-librarian/install.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("/api/chat", installer)
        self.assertIn("done_reason", installer)
        self.assertIn("Bot-to-Ollama structured analysis smoke", installer)
        self.assertIn("exec -T bot python", installer)

    def test_start_does_not_require_network_when_sources_exist(self) -> None:
        start = (ROOT / "deploy/hermes-librarian/start.sh").read_text(
            encoding="utf-8"
        )
        self.assertGreaterEqual(start.count("if !"), 2)
        self.assertGreaterEqual(start.count("ollama show \"$"), 2)
        self.assertEqual(2, start.count("ollama pull"))


if __name__ == "__main__":
    unittest.main()
