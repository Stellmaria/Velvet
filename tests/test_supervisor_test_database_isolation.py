from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from velvet_bot.database import _isolated_test_schema
from velvet_supervisor.git_ops import GitRepository


class IsolatedPostgresSchemaTests(unittest.TestCase):
    def test_unittest_gets_private_schema(self) -> None:
        url = "postgresql://tester:secret@localhost/velvet_test"
        with patch.dict(os.environ, {"TEST_DATABASE_URL": url}, clear=False), patch.object(
  sys, "argv", ["python", "-m", "unittest", "discover"]
        ):
  schema = _isolated_test_schema(url)
        self.assertIsNotNone(schema)
        assert schema is not None
        self.assertTrue(schema.startswith("velvet_test_"))
        self.assertLessEqual(len(schema), 63)

    def test_production_process_does_not_switch_schema(self) -> None:
        url = "postgresql://tester:secret@localhost/velvet_test"
        with patch.dict(os.environ, {"TEST_DATABASE_URL": url}, clear=False), patch.object(
  sys, "argv", ["python", "main.py"]
        ):
  self.assertIsNone(_isolated_test_schema(url))

    def test_invalid_explicit_schema_is_rejected(self) -> None:
        url = "postgresql://tester:secret@localhost/velvet_test"
        with patch.dict(
  os.environ,
  {"TEST_DATABASE_URL": url, "TEST_DATABASE_SCHEMA": "bad-schema;drop"},
  clear=False,
        ), patch.object(sys, "argv", ["python", "-m", "unittest"]):
  with self.assertRaisesRegex(RuntimeError, "identifier"):
      _isolated_test_schema(url)


class SupervisorTestEnvironmentTests(unittest.TestCase):
    def _repository(self, test_database_url: str | None) -> GitRepository:
        return GitRepository(
  Path("."),
  timeout_seconds=30,
  test_command=("python", "-m", "unittest"),
  test_database_url=test_database_url,
        )

    def test_inherited_test_database_is_removed(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="ok")
        with patch.dict(
  os.environ, {"TEST_DATABASE_URL": "postgresql://wrong/database"}, clear=False
        ), patch("velvet_supervisor.git_ops.subprocess.run", return_value=completed) as runner:
  self._repository(None).run_tests()
        environment = runner.call_args.kwargs["env"]
        self.assertNotIn("TEST_DATABASE_URL", environment)

    def test_explicit_supervisor_test_database_is_forwarded(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="ok")
        dedicated = "postgresql://tester/dedicated"
        with patch("velvet_supervisor.git_ops.subprocess.run", return_value=completed) as runner:
  self._repository(dedicated).run_tests()
        self.assertEqual(dedicated, runner.call_args.kwargs["env"]["TEST_DATABASE_URL"])


if __name__ == "__main__":
    unittest.main()
