import unittest


class ApplicationImportTests(unittest.TestCase):
    def test_main_and_handlers_import(self) -> None:
        import main  # noqa: F401
        import velvet_bot.handlers  # noqa: F401


if __name__ == "__main__":
    unittest.main()
