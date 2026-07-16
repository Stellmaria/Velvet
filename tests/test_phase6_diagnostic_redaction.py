import unittest

from velvet_bot.services.system_health import SystemHealthService


class DiagnosticRedactionTests(unittest.TestCase):
    def test_connection_url_bot_token_and_assignments_are_redacted(self) -> None:
        source = (
            "failed DATABASE_URL=postgresql://velvet:password@localhost:5432/velvet "
            "token 8903084324:abcdefghijklmnopqrstuvwxyzABCDE "
            "API_KEY=super-secret-value"
        )
        redacted = SystemHealthService.redact_text(source)

        self.assertNotIn("password", redacted)
        self.assertNotIn("8903084324:", redacted)
        self.assertNotIn("super-secret-value", redacted)
        self.assertIn("<redacted-secret>", redacted)
        self.assertIn("<redacted-bot-token>", redacted)

    def test_none_remains_none(self) -> None:
        self.assertIsNone(SystemHealthService.redact_text(None))


if __name__ == "__main__":
    unittest.main()
