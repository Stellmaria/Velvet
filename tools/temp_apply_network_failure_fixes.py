from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    source = target.read_text(encoding="utf-8")
    if old not in source:
        raise RuntimeError(f"Expected block not found in {path}: {old[:120]!r}")
    target.write_text(source.replace(old, new, 1), encoding="utf-8")


def patch_runtime_stability() -> None:
    path = "velvet_bot/runtime_stability.py"
    replace(
        path,
        "_BACKOFF_MARKERS = (\n    \"sleep for \",\n    \" seconds and try again\",\n)\n",
        "_BACKOFF_MARKERS = (\n    \"sleep for \",\n    \" seconds and try again\",\n)\n\n_ASYNCIO_CLOSE_NETWORK_MARKERS = (\n    \"connectionabortederror\",\n    \"connectionreseterror\",\n    \"brokenpipeerror\",\n    \"подключение к сети было разорвано\",\n    \"connection was closed in the middle of operation\",\n    \"connection reset by peer\",\n)\n_LOOP_GUARD_INSTALLED: set[int] = set()\n",
    )
    replace(
        path,
        "def is_recoverable_aiogram_polling_record(record: logging.LogRecord) -> bool:\n    \"\"\"Return True for transient Telegram polling noise that aiogram retries itself.\"\"\"\n\n    if record.name != \"aiogram.dispatcher\":\n        return False\n\n    message = _record_message(record)\n",
        "def is_recoverable_aiogram_polling_record(record: logging.LogRecord) -> bool:\n    \"\"\"Return True for transient transport noise already handled by a retry loop.\"\"\"\n\n    message = _record_message(record)\n    if record.name == \"asyncio\":\n        return (\n            \"task exception was never retrieved\" in message\n            and \"connection.close()\" in message\n            and any(marker in message for marker in _ASYNCIO_CLOSE_NETWORK_MARKERS)\n        )\n    if record.name != \"aiogram.dispatcher\":\n        return False\n\n",
    )
    marker = "\n\nasync def acknowledge_legacy_polling_noise(repository: Any) -> int:\n"
    insert = '''\n\ndef is_recoverable_asyncio_connection_close_context(\n    context: dict[str, Any],\n) -> bool:\n    \"\"\"Identify asyncpg close tasks that fail only because the socket already died.\"\"\"\n\n    message = str(context.get(\"message\") or \"\").casefold()\n    future = context.get(\"future\") or context.get(\"task\")\n    future_text = repr(future).casefold()\n    error = context.get(\"exception\")\n    error_text = f\"{type(error).__name__}: {error}\".casefold() if error else \"\"\n    return (\n        \"task exception was never retrieved\" in message\n        and \"connection.close()\" in future_text\n        and any(marker in error_text for marker in _ASYNCIO_CLOSE_NETWORK_MARKERS)\n    )\n\n\ndef install_asyncio_exception_guard(loop: asyncio.AbstractEventLoop) -> None:\n    \"\"\"Suppress only the known asyncpg close-after-network-drop task failure.\"\"\"\n\n    identity = id(loop)\n    if identity in _LOOP_GUARD_INSTALLED:\n        return\n    previous = loop.get_exception_handler()\n\n    def handle(\n        current_loop: asyncio.AbstractEventLoop,\n        context: dict[str, Any],\n    ) -> None:\n        if is_recoverable_asyncio_connection_close_context(context):\n            logger.info(\n                \"Ignored transient asyncpg connection close failure: %s\",\n                context.get(\"exception\"),\n            )\n            return\n        if previous is not None:\n            previous(current_loop, context)\n        else:\n            current_loop.default_exception_handler(context)\n\n    loop.set_exception_handler(handle)\n    _LOOP_GUARD_INSTALLED.add(identity)\n'''
    replace(path, marker, insert + marker)
    replace(
        path,
        "           OR (\n               logger_name = 'velvet_bot.presentation.telegram.router'\n               AND LOWER(summary) LIKE '%unhandled bot error%'\n               AND (\n                      LOWER(summary) LIKE '%clientconnectorerror%'\n                   OR LOWER(summary) LIKE '%cannot connect to host api.telegram.org%'\n                   OR LOWER(summary) LIKE '%превышен таймаут семафора%'\n                   OR LOWER(summary) LIKE '%подключение к сети было разорвано%'\n                   OR LOWER(summary) LIKE '%semaphore timeout%'\n                   OR LOWER(summary) LIKE '%connection reset by peer%'\n                   OR LOWER(summary) LIKE '%connection timed out%'\n               )\n           )\n",
        "           OR (\n               logger_name = 'velvet_bot.presentation.telegram.router'\n               AND LOWER(summary) LIKE '%unhandled bot error%'\n               AND (\n                      LOWER(summary) LIKE '%clientconnectorerror%'\n                   OR LOWER(summary) LIKE '%cannot connect to host api.telegram.org%'\n                   OR LOWER(summary) LIKE '%превышен таймаут семафора%'\n                   OR LOWER(summary) LIKE '%подключение к сети было разорвано%'\n                   OR LOWER(summary) LIKE '%semaphore timeout%'\n                   OR LOWER(summary) LIKE '%connection reset by peer%'\n                   OR LOWER(summary) LIKE '%connection timed out%'\n               )\n           )\n           OR (\n               logger_name = 'asyncio'\n               AND LOWER(summary) LIKE '%task exception was never retrieved%'\n               AND LOWER(summary) LIKE '%connection.close()%'\n               AND (\n                      LOWER(summary) LIKE '%connectionabortederror%'\n                   OR LOWER(summary) LIKE '%connectionreseterror%'\n                   OR LOWER(summary) LIKE '%подключение к сети было разорвано%'\n                   OR LOWER(summary) LIKE '%connection was closed in the middle of operation%'\n               )\n           )\n",
    )
    replace(
        path,
        "    async def start_with_polling_cleanup(self) -> None:\n        try:\n",
        "    async def start_with_polling_cleanup(self) -> None:\n        install_asyncio_exception_guard(asyncio.get_running_loop())\n        try:\n",
    )
    replace(
        path,
        "    \"acknowledge_legacy_polling_noise\",\n    \"install_runtime_stability\",\n    \"is_recoverable_aiogram_polling_record\",\n",
        "    \"acknowledge_legacy_polling_noise\",\n    \"install_asyncio_exception_guard\",\n    \"install_runtime_stability\",\n    \"is_recoverable_aiogram_polling_record\",\n    \"is_recoverable_asyncio_connection_close_context\",\n",
    )


def patch_codex() -> None:
    path = "velvet_supervisor/codex.py"
    replace(path, "import logging\nimport threading\n", "import logging\nimport re\nimport threading\n")
    marker = "logger = logging.getLogger(__name__)\n"
    helper = '''logger = logging.getLogger(__name__)\n\n_HTML_TAG_RE = re.compile(r\"<[^>]+>\")\n\n\ndef summarize_codex_failure(error: BaseException) -> str:\n    \"\"\"Return a short actionable message instead of proxy HTML/CSS noise.\"\"\"\n\n    raw = str(error).strip()\n    folded = raw.casefold()\n    if \"403 forbidden\" in folded and (\n        \"backend-api/codex/responses\" in folded or \"cf-ray\" in folded\n    ):\n        return (\n            \"Codex получил 403 Forbidden от ChatGPT до запуска работы с кодом.\\n\"\n            \"Вероятная причина: локальная авторизация Codex истекла либо запрос \"\n            \"заблокирован сетью или Cloudflare.\\n\\n\"\n            \"На компьютере Supervisor выполните `codex --login`, затем \"\n            \"перезапустите Supervisor и повторите задачу. Если вход уже выполнен, \"\n            \"проверьте доступ к chatgpt.com без проблемного VPN или прокси.\"\n        )\n    if \"<html\" in folded or \"<!doctype html\" in folded:\n        return (\n            \"Codex вернул HTML-страницу вместо API-ответа. Это сетевой или \"\n            \"авторизационный отказ, а не ошибка кода проекта. Повторите вход через \"\n            \"`codex --login` и проверьте соединение.\"\n        )\n    compact = \" \".join(_HTML_TAG_RE.sub(\" \", raw).split())\n    return (compact[-3000:] if compact else type(error).__name__)\n'''
    replace(path, marker, helper)
    replace(
        path,
        "        except Exception as error:\n            logger.exception(\"Codex task failed id=%s\", task_id)\n            self._update(\n                task_id,\n                status=\"error\",\n                error=str(error)[:10000],\n                finished_at=utc_now(),\n            )\n            self._notifier.send(\n                \"Ошибка задачи Codex\",\n                f\"Задача: {task_id}\\n{str(error)[-3000:]}\",\n                level=\"ERROR\",\n            )\n",
        "        except Exception as error:\n            logger.exception(\"Codex task failed id=%s\", task_id)\n            summary = summarize_codex_failure(error)\n            self._update(\n                task_id,\n                status=\"error\",\n                error=summary[:10000],\n                finished_at=utc_now(),\n            )\n            self._notifier.send(\n                \"Ошибка задачи Codex\",\n                f\"Задача: {task_id}\\n{summary}\",\n                level=\"ERROR\",\n            )\n",
    )
    replace(path, '__all__ = ("CodexTaskManager",)\n', '__all__ = ("CodexTaskManager", "summarize_codex_failure")\n')


def patch_dependencies() -> None:
    path = "velvet_supervisor/dependencies.py"
    replace(path, "import subprocess\n", "import subprocess\nimport time\n")
    marker = "\n\ndef _sync_text(\n"
    helper = '''\n\n_TRANSIENT_GIT_NETWORK_MARKERS = (\n    \"couldn't connect to server\",\n    \"failed to connect to github.com\",\n    \"could not resolve host\",\n    \"connection reset by peer\",\n    \"connection timed out\",\n    \"the requested url returned error: 502\",\n    \"the requested url returned error: 503\",\n    \"the requested url returned error: 504\",\n)\n\n\ndef _run_git_with_retries(\n    command: tuple[str, ...],\n    *,\n    cwd: Path,\n    timeout_seconds: int,\n    attempts: int = 3,\n) -> subprocess.CompletedProcess[str]:\n    result: subprocess.CompletedProcess[str] | None = None\n    for attempt in range(max(1, attempts)):\n        result = _run(command, cwd=cwd, timeout_seconds=timeout_seconds)\n        output = (result.stdout or \"\").casefold()\n        transient = any(marker in output for marker in _TRANSIENT_GIT_NETWORK_MARKERS)\n        if result.returncode == 0 or not transient or attempt + 1 >= attempts:\n            return result\n        time.sleep((1.0, 3.0)[min(attempt, 1)])\n    assert result is not None\n    return result\n'''
    replace(path, marker, helper + marker)
    replace(
        path,
        "    fetch = _run(\n        (\"git\", \"fetch\", \"--prune\", remote, branch),\n        cwd=project_dir,\n        timeout_seconds=timeout,\n    )\n",
        "    fetch = _run_git_with_retries(\n        (\"git\", \"fetch\", \"--prune\", remote, branch),\n        cwd=project_dir,\n        timeout_seconds=timeout,\n    )\n",
    )
    replace(
        path,
        "            \"Не удалось получить удалённую ветку перед синхронизацией зависимостей.\\n\"\n",
        "            \"Не удалось получить удалённую ветку после трёх попыток перед синхронизацией зависимостей.\\n\"\n",
    )


def patch_git_ops() -> None:
    path = "velvet_supervisor/git_ops.py"
    replace(path, "import subprocess\n", "import subprocess\nimport time\n")
    replace(
        path,
        "    def fetch(self, remote: str, branch: str) -> str:\n        return self.git(\"fetch\", \"--prune\", remote, branch).output\n",
        '''    def fetch(self, remote: str, branch: str) -> str:\n        last: CommandResult | None = None\n        markers = (\n            \"couldn't connect to server\",\n            \"failed to connect to github.com\",\n            \"could not resolve host\",\n            \"connection reset by peer\",\n            \"connection timed out\",\n            \"the requested url returned error: 502\",\n            \"the requested url returned error: 503\",\n            \"the requested url returned error: 504\",\n        )\n        for attempt in range(3):\n            last = self.git(\n                \"fetch\",\n                \"--prune\",\n                remote,\n                branch,\n                check=False,\n            )\n            output = last.output.casefold()\n            transient = any(marker in output for marker in markers)\n            if last.returncode == 0:\n                return last.output\n            if not transient or attempt == 2:\n                raise CommandError(last.command, last.returncode, last.output)\n            time.sleep((1.0, 3.0)[min(attempt, 1)])\n        raise RuntimeError(\"Git fetch retry loop ended unexpectedly.\")\n''',
    )


def patch_bootstrap() -> None:
    path = "velvet_supervisor/bootstrap.py"
    marker = "\n\ndef _test_environment(settings: SupervisorSettings) -> dict[str, str]:\n"
    helper = '''\n\n_TRANSIENT_GIT_NETWORK_MARKERS = (\n    \"couldn't connect to server\",\n    \"failed to connect to github.com\",\n    \"could not resolve host\",\n    \"connection reset by peer\",\n    \"connection timed out\",\n    \"the requested url returned error: 502\",\n    \"the requested url returned error: 503\",\n    \"the requested url returned error: 504\",\n)\n\n\ndef _run_git_with_retries(\n    command: Sequence[str],\n    *,\n    cwd: Path,\n    timeout: int,\n) -> subprocess.CompletedProcess[str]:\n    completed: subprocess.CompletedProcess[str] | None = None\n    for attempt in range(3):\n        completed = _run(command, cwd=cwd, timeout=timeout, check=False)\n        output = (completed.stdout or \"\").casefold()\n        transient = any(marker in output for marker in _TRANSIENT_GIT_NETWORK_MARKERS)\n        if completed.returncode == 0:\n            return completed\n        if not transient or attempt == 2:\n            raise RuntimeError(\n                f\"Команда завершилась с кодом {completed.returncode}: \"\n                f\"{subprocess.list2cmdline(command)}\\n{completed.stdout[-5000:]}\"\n            )\n        time.sleep((1.0, 3.0)[min(attempt, 1)])\n    assert completed is not None\n    return completed\n'''
    replace(path, marker, helper + marker)
    replace(
        path,
        "    _run(\n        (\"git\", \"fetch\", settings.update_remote),\n        cwd=project_dir,\n        timeout=settings.command_timeout_seconds,\n    )\n",
        "    _run_git_with_retries(\n        (\"git\", \"fetch\", settings.update_remote),\n        cwd=project_dir,\n        timeout=settings.command_timeout_seconds,\n    )\n",
    )
    replace(
        path,
        "    _run(\n        (\"git\", \"pull\", \"--ff-only\", settings.update_remote, settings.update_branch),\n        cwd=project_dir,\n        timeout=settings.command_timeout_seconds,\n    )\n",
        "    _run_git_with_retries(\n        (\"git\", \"pull\", \"--ff-only\", settings.update_remote, settings.update_branch),\n        cwd=project_dir,\n        timeout=settings.command_timeout_seconds,\n    )\n",
    )


def patch_tests() -> None:
    path = ROOT / "tests/test_network_failure_handling.py"
    path.write_text(
        '''from __future__ import annotations\n\nimport asyncio\nimport logging\nimport subprocess\nimport tempfile\nimport unittest\nfrom pathlib import Path\nfrom types import SimpleNamespace\nfrom unittest.mock import patch\n\nfrom velvet_bot import runtime_stability\nfrom velvet_supervisor.codex import summarize_codex_failure\nfrom velvet_supervisor.dependencies import sync_remote_requirements\n\n\nclass NetworkFailureHandlingTests(unittest.TestCase):\n    def test_codex_403_is_actionable_and_does_not_include_html(self) -> None:\n        message = summarize_codex_failure(\n            RuntimeError(\n                \"unexpected status 403 Forbidden: <html><style>.data{color:red}</style>\"\n                \", url: https://chatgpt.com/backend-api/codex/responses, cf-ray: test\"\n            )\n        )\n        self.assertIn(\"403 Forbidden\", message)\n        self.assertIn(\"codex --login\", message)\n        self.assertNotIn(\"<html>\", message)\n        self.assertNotIn(\".data{\", message)\n\n    def test_asyncpg_close_after_network_drop_is_recoverable(self) -> None:\n        async def close() -> None:\n            return None\n\n        loop = asyncio.new_event_loop()\n        try:\n            task = loop.create_task(close(), name=\"close-test\")\n            loop.run_until_complete(task)\n            fake = SimpleNamespace()\n            fake.__repr__ = lambda self: \"<Task coro=<Connection.close() done>>\"\n            context = {\n                \"message\": \"Task exception was never retrieved\",\n                \"future\": _FutureRepr(),\n                \"exception\": ConnectionAbortedError(1236, \"Подключение к сети было разорвано локальной системой\"),\n            }\n            self.assertTrue(\n                runtime_stability.is_recoverable_asyncio_connection_close_context(context)\n            )\n        finally:\n            loop.close()\n\n    def test_asyncio_log_record_is_filtered(self) -> None:\n        record = logging.LogRecord(\n            \"asyncio\",\n            logging.ERROR,\n            \"test.py\",\n            1,\n            \"Task exception was never retrieved future=<Task coro=<Connection.close() done>> exception=ConnectionAbortedError: Подключение к сети было разорвано\",\n            (),\n            None,\n        )\n        self.assertTrue(runtime_stability.is_recoverable_aiogram_polling_record(record))\n\n    def test_remote_requirements_fetch_retries_transient_network_failure(self) -> None:\n        with tempfile.TemporaryDirectory() as directory:\n            root = Path(directory)\n            settings = SimpleNamespace(\n                project_dir=root,\n                runtime_dir=root / \"runtime\",\n                python_executable=\"python\",\n                command_timeout_seconds=30,\n                update_remote=\"origin\",\n                update_branch=\"main\",\n            )\n            calls = 0\n\n            def fake_run(command, **kwargs):\n                nonlocal calls\n                if command[:2] == (\"git\", \"fetch\"):\n                    calls += 1\n                    if calls < 3:\n                        return subprocess.CompletedProcess(\n                            command, 1, stdout=\"Failed to connect to github.com\"\n                        )\n                    return subprocess.CompletedProcess(command, 0, stdout=\"ok\")\n                if command[:2] == (\"git\", \"show\"):\n                    return subprocess.CompletedProcess(\n                        command, 0, stdout=\"aiogram==3.29.1\\n\"\n                    )\n                return subprocess.CompletedProcess(command, 0, stdout=\"installed\")\n\n            with patch(\"velvet_supervisor.dependencies._run\", side_effect=fake_run), patch(\n                \"velvet_supervisor.dependencies.time.sleep\"\n            ):\n                result = sync_remote_requirements(settings)\n\n            self.assertEqual(3, calls)\n            self.assertTrue(result.installed)\n\n\nclass _FutureRepr:\n    def __repr__(self) -> str:\n        return \"<Task finished coro=<Connection.close() done>>\"\n\n\nif __name__ == \"__main__\":\n    unittest.main()\n''',
        encoding="utf-8",
    )


if __name__ == "__main__":
    patch_runtime_stability()
    patch_codex()
    patch_dependencies()
    patch_git_ops()
    patch_bootstrap()
    patch_tests()
