from __future__ import annotations

import json
import os
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from velvet_bot.application.storage_librarian import (
    _fallback_analysis_rows,
    _search_terms,
)
from velvet_bot.domains.telegram_storage.librarian_content import (
    extract_storage_text,
    parse_librarian_analysis,
    redact_sensitive,
)
from velvet_bot.domains.telegram_storage.librarian_models import (
    LibrarianAnalysis,
    LibrarianObject,
    StorageLibrarianSettings,
    TerminalStorageLibrarianError,
    storage_librarian_text_prompt_char_limit,
    storage_librarian_text_source_char_limit,
)
from velvet_bot.infrastructure.telegram.storage_librarian_reports import (
    build_storage_librarian_report,
)


ROOT = Path(__file__).resolve().parents[1]


class StorageLibrarianMigrationContractTests(unittest.TestCase):
    def test_migration_adds_librarian_queue_and_analysis_tables(self) -> None:
        sql = (ROOT / "migrations" / "z031_telegram_storage_librarian.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("telegram_storage_analysis_jobs", sql)
        self.assertIn("telegram_storage_analysis", sql)
        self.assertIn("'inbox'", sql)
        self.assertIn("'analysis'", sql)

    def test_owner_router_registers_librarian(self) -> None:
        source = (
            ROOT
            / "velvet_bot"
            / "presentation"
            / "telegram"
            / "routers"
            / "core_operations_controllers"
            / "owner_menu.py"
        ).read_text(encoding="utf-8")
        self.assertIn("register_storage_librarian(router)", source)

    def test_manual_analysis_does_not_bulk_enqueue_archive(self) -> None:
        source = (
            ROOT
            / "velvet_bot"
            / "presentation"
            / "telegram"
            / "storage_librarian.py"
        ).read_text(encoding="utf-8")
        self.assertIn("process_once(auto_enqueue=False)", source)
        self.assertIn("STORAGE_LIBRARIAN_AUTO_ENQUEUE", source)

    def test_reports_are_explicit_and_use_dedicated_topic_publisher(self) -> None:
        presentation = (
            ROOT
            / "velvet_bot"
            / "presentation"
            / "telegram"
            / "storage_librarian.py"
        ).read_text(encoding="utf-8")
        publisher = (
            ROOT
            / "velvet_bot"
            / "infrastructure"
            / "telegram"
            / "storage_librarian_reports.py"
        ).read_text(encoding="utf-8")
        installer = (
            ROOT / "deploy" / "hermes-librarian" / "install.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("STORAGE_LIBRARIAN_PUBLISH_REPORTS", presentation)
        self.assertIn("TelegramStorageLibrarianReportPublisher", presentation)
        self.assertIn('threads.for_kind("analysis")', publisher)
        self.assertIn("STORAGE_LIBRARIAN_PUBLISH_REPORTS", installer)
        self.assertIn("velvet-librarian:qwen3-4b-text:v4", installer)
        self.assertIn("context_compiler.py", installer)
        self.assertIn("context-manifest.json", installer)

    def test_local_runtime_is_private_pinned_and_without_cloud_fallback(self) -> None:
        compose = (ROOT / "deploy/hermes-librarian/compose.yaml").read_text(
            encoding="utf-8"
        )
        profile = (ROOT / "deploy/hermes-librarian/prepare_profile.py").read_text(
            encoding="utf-8"
        )
        start = (ROOT / "deploy/hermes-librarian/start.sh").read_text(
            encoding="utf-8"
        )
        installer = (ROOT / "deploy/hermes-librarian/install.sh").read_text(
            encoding="utf-8"
        )
        text_modelfile = (ROOT / "deploy/hermes-librarian/Modelfile.text").read_text(
            encoding="utf-8"
        )
        vision_modelfile = (ROOT / "deploy/hermes-librarian/Modelfile.vision").read_text(
            encoding="utf-8"
        )
        self.assertIn("ollama/ollama:0.32.3", compose)
        self.assertIn("ollama-librarian", compose)
        self.assertIn("librarian-ollama:/root/.ollama", compose)
        self.assertNotIn("ports:", compose)
        self.assertIn('"provider": "custom"', profile)
        self.assertIn('config["fallback_providers"] = []', profile)
        self.assertIn("ollama pull", start)
        self.assertIn("qwen3:4b-instruct", text_modelfile)
        self.assertIn("PARAMETER num_ctx 8192", text_modelfile)
        self.assertIn("PARAMETER num_predict 384", text_modelfile)
        self.assertIn("PARAMETER temperature 0", text_modelfile)
        self.assertIn("qwen3.5:9b-q4_K_M", vision_modelfile)
        self.assertIn("PARAMETER num_ctx 16384", vision_modelfile)
        self.assertIn("PARAMETER num_predict 640", vision_modelfile)
        self.assertIn("velvet-librarian-text:v1", start)
        self.assertIn("velvet-librarian-vision:v1", start)
        self.assertGreaterEqual(start.count("ollama pull"), 2)
        self.assertGreaterEqual(start.count("ollama create"), 2)
        self.assertGreaterEqual(start.count("ollama show"), 2)
        self.assertIn('values.get(', start)
        self.assertIn('"STORAGE_LIBRARIAN_TEXT_MODEL"', start)
        self.assertIn('"STORAGE_LIBRARIAN_VISION_MODEL"', start)
        self.assertNotIn('os.environ["STORAGE_LIBRARIAN_LOCAL_MODEL"]', installer)
        self.assertNotIn('os.environ["STORAGE_LIBRARIAN_LOCAL_BASE_URL"]', installer)
        self.assertNotIn("STORAGE_LIBRARIAN_MAX_TEXT_CHARS:-120000", compose)
        self.assertIn(
            'STORAGE_LIBRARIAN_MAX_TEXT_CHARS: "${STORAGE_LIBRARIAN_MAX_TEXT_CHARS:-}"',
            compose,
        )

    def test_kael_installer_checks_runtime_user_not_root_exec(self) -> None:
        installer = (
            ROOT / "deploy" / "hermes-entities" / "install.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("/command/s6-setuidgid hermes", installer)
        self.assertIn('test "$(id -u)" = "10000"', installer)

    def test_librarian_is_split_across_architecture_layers(self) -> None:
        old_monolith = (
            ROOT
            / "velvet_bot"
            / "domains"
            / "telegram_storage"
            / "librarian.py"
        )
        self.assertFalse(old_monolith.exists())
        expected = (
            ROOT / "velvet_bot" / "application" / "storage_librarian.py",
            ROOT
            / "velvet_bot"
            / "domains"
            / "telegram_storage"
            / "librarian_repository.py",
            ROOT
            / "velvet_bot"
            / "infrastructure"
            / "telegram"
            / "storage_librarian_files.py",
            ROOT
            / "velvet_bot"
            / "infrastructure"
            / "telegram"
            / "storage_librarian_reports.py",
            ROOT
            / "velvet_bot"
            / "infrastructure"
            / "ai"
            / "storage_librarian_hermes.py",
        )
        self.assertTrue(all(path.is_file() for path in expected))


class StorageLibrarianSettingsTests(unittest.TestCase):
    def test_disabled_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = StorageLibrarianSettings.from_env()
        self.assertFalse(settings.enabled)
        self.assertNotIn("backups", settings.allowed_kinds)
        self.assertNotIn("watermarks", settings.allowed_kinds)
        self.assertEqual(
            "velvet-librarian:qwen3-4b-text:v4",
            settings.analyzer_version,
        )
        self.assertEqual(180, settings.run_timeout_seconds)
        self.assertEqual(
            13_568,
            storage_librarian_text_prompt_char_limit(
                context_length=8192,
                max_output_tokens=384,
            ),
        )
        self.assertEqual(
            11_520,
            storage_librarian_text_source_char_limit(
                context_length=8192,
                max_output_tokens=384,
            ),
        )
        self.assertEqual(11_520, settings.max_text_chars)

    def test_text_limit_tracks_context_and_clamps_legacy_override(self) -> None:
        with patch.dict(
            os.environ,
            {
                "STORAGE_LIBRARIAN_TEXT_CONTEXT_LENGTH": "4096",
                "STORAGE_LIBRARIAN_TEXT_MAX_OUTPUT_TOKENS": "256",
            },
            clear=True,
        ):
            settings = StorageLibrarianSettings.from_env()
        self.assertEqual(3584, settings.max_text_chars)

        with patch.dict(
            os.environ,
            {"STORAGE_LIBRARIAN_MAX_TEXT_CHARS": "120000"},
            clear=True,
        ):
            settings = StorageLibrarianSettings.from_env()
        self.assertEqual(11_520, settings.max_text_chars)

        with patch.dict(
            os.environ,
            {"STORAGE_LIBRARIAN_MAX_TEXT_CHARS": "8000"},
            clear=True,
        ):
            settings = StorageLibrarianSettings.from_env()
        self.assertEqual(8000, settings.max_text_chars)

    def test_protected_storage_kinds_are_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {"STORAGE_LIBRARIAN_ALLOWED_KINDS": "diagnostics,backups"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "защищённые категории"):
                StorageLibrarianSettings.from_env()


class StorageLibrarianSearchTests(unittest.TestCase):
    def test_russian_inflections_find_error_summary(self) -> None:
        candidates = [
            {
                "storage_object_id": 2143,
                "storage_kind": "diagnostics",
                "logical_key": "diagnostics:logs:server-supervisor.log",
                "original_name": "server-supervisor.log",
                "summary": (
                    "Проверки health прошли успешно, ошибок в предоставленном "
                    "фрагменте нет."
                ),
                "tags": ["health-check", "server-supervisor"],
                "entities": [],
                "action_items": [],
                "analyzed_at": "2026-08-02T01:04:00Z",
            },
            {
                "storage_object_id": 2134,
                "storage_kind": "diagnostics",
                "logical_key": "diagnostics:logs:server-supervisor.log",
                "original_name": "server-supervisor.log",
                "summary": (
                    "Ранний update завершился ошибкой read-only filesystem и "
                    "автоматическим откатом deployment."
                ),
                "tags": ["update-failure", "read-only-filesystem"],
                "entities": [],
                "action_items": [],
                "analyzed_at": "2026-08-02T00:10:00Z",
            },
        ]
        rows = _fallback_analysis_rows(
            "какие ошибки и предупреждения повторялись?",
            candidates,
            limit=8,
        )
        self.assertIn("ошибк", _search_terms("какие ошибки повторялись?"))
        self.assertEqual([2134], [row["storage_object_id"] for row in rows])

    def test_unrelated_question_does_not_return_random_recent_rows(self) -> None:
        rows = _fallback_analysis_rows(
            "какие платежи были по подпискам?",
            [
                {
                    "storage_object_id": 2149,
                    "summary": "Запуск монитора инцидентов Hermes.",
                    "tags": ["diagnostics"],
                    "entities": [],
                    "action_items": [],
                    "logical_key": "diagnostics:monitor",
                    "original_name": "monitor.log",
                }
            ],
            limit=8,
        )
        self.assertEqual([], rows)


class StorageLibrarianPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = StorageLibrarianSettings(
            enabled=False,
            hermes_base_url="http://hermes:8642",
            hermes_api_key=None,
            scan_interval_seconds=300,
            poll_interval_seconds=2,
            run_timeout_seconds=300,
            max_object_bytes=1024 * 1024,
            max_text_chars=20_000,
            max_zip_entries=20,
            max_attempts=3,
            analyzer_version="test:v1",
            allowed_kinds=("diagnostics",),
        )

    def test_json_object_is_rendered_with_manifest(self) -> None:
        payload = json.dumps({"error": "timeout", "count": 3}).encode("utf-8")
        item = LibrarianObject(
            object_id=7,
            storage_kind="diagnostics",
            logical_key="diagnostics:errors:7",
            original_name="errors.json",
            mime_type="application/json",
            size_bytes=len(payload),
            sha256="a" * 64,
            encrypted=False,
            manifest={"source": "test"},
            parts=(),
        )
        result = extract_storage_text(item, payload, settings=self.settings)
        self.assertIn('"error": "timeout"', result)
        self.assertIn('"source": "test"', result)
        self.assertIn("Storage ID: 7", result)

    def test_oversized_source_fails_closed_instead_of_truncating(self) -> None:
        settings = replace(self.settings, max_text_chars=2000)
        payload = ("x" * 2500).encode("utf-8")
        item = LibrarianObject(
            object_id=8,
            storage_kind="diagnostics",
            logical_key="diagnostics:oversized:8",
            original_name="oversized.log",
            mime_type="text/plain",
            size_bytes=len(payload),
            sha256="c" * 64,
            encrypted=False,
            manifest={},
            parts=(),
        )
        with self.assertRaisesRegex(TerminalStorageLibrarianError, "silent truncation"):
            extract_storage_text(item, payload, settings=settings)

    def test_analysis_json_is_normalized(self) -> None:
        result = parse_librarian_analysis(
            """```json
            {
              "summary": "Повторяется timeout",
              "tags": ["timeout", "network"],
              "entities": [{"name": "Kie", "type": "provider"}],
              "action_items": [{"text": "Проверить retry", "priority": "high"}],
              "sensitivity": "normal",
              "confidence": 91
            }
            ```"""
        )
        self.assertEqual(result.summary, "Повторяется timeout")
        self.assertEqual(result.tags, ("timeout", "network"))
        self.assertEqual(result.confidence, 91)
        self.assertEqual(result.action_items[0]["priority"], "high")

    def test_sensitive_values_are_redacted(self) -> None:
        value = redact_sensitive(
            "BOT_TOKEN=123456789:" + "abcdefghijklmnopqrstuvwxyzABCDE "
            "DATABASE_URL=postgresql://velvet:secret@postgres:5432/velvet"
        )
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", value)
        self.assertNotIn(":secret@", value)
        self.assertIn("[REDACTED]", value)

    def test_report_is_bounded_escaped_and_references_storage_id(self) -> None:
        item = LibrarianObject(
            object_id=2149,
            storage_kind="diagnostics",
            logical_key="diagnostics:logs:incident",
            original_name="incident<script>.log",
            mime_type="text/plain",
            size_bytes=238,
            sha256="b" * 64,
            encrypted=False,
            manifest={},
            parts=(),
        )
        analysis = LibrarianAnalysis(
            summary="Повторные запуски <b>монитора</b>.",
            tags=("diagnostics", "hermes"),
            entities=(),
            action_items=(
                {"title": "Проверить дедупликацию", "priority": "high"},
            ),
            sensitivity="normal",
            confidence=88,
            raw={},
        )
        text = build_storage_librarian_report(item, analysis)
        self.assertLessEqual(len(text), 4000)
        self.assertIn("Storage ID: <code>2149</code>", text)
        self.assertIn("/storage_download 2149", text)
        self.assertIn("Проверить дедупликацию", text)
        self.assertNotIn("<script>", text)
        self.assertNotIn("<b>монитора</b>", text)


if __name__ == "__main__":
    unittest.main()
