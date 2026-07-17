from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "velvet_supervisor/bootstrap.py"
TESTS = ROOT / "tests/test_supervisor_remote_runtime.py"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: ожидалось одно совпадение, найдено {count}")
    return source.replace(old, new, 1)


def patch_bootstrap() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")
    source = replace_once(
        source,
        "import subprocess\nimport time\n",
        "import subprocess\nimport time\nimport urllib.error\nimport urllib.request\n",
        "urllib imports",
    )
    source = replace_once(
        source,
        "from .config import SupervisorSettings\nfrom .notifier import TelegramNotifier\n",
        "from .config import SupervisorSettings\n"
        "from .models import JsonStateStore\n"
        "from .notifier import TelegramNotifier\n",
        "state store import",
    )

    marker = "def _result_path(settings: SupervisorSettings) -> Path:\n"
    helpers = r'''def _lock_path(settings: SupervisorSettings) -> Path:
    return settings.runtime_dir / "bootstrap.lock"


def _acquire_lock(settings: SupervisorSettings, operation_id: str) -> None:
    path = _lock_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        age = max(0.0, time.time() - path.stat().st_mtime)
        if age < 15 * 60:
            owner = path.read_text(encoding="utf-8", errors="replace").strip()
            raise RuntimeError(
                f"Уже выполняется bootstrap-операция {owner or 'unknown'}."
            )
        path.unlink(missing_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(operation_id)
    except FileExistsError as error:
        raise RuntimeError("Bootstrap уже запущен другим запросом.") from error


def _release_lock(settings: SupervisorSettings) -> None:
    _lock_path(settings).unlink(missing_ok=True)


def _resolved_python(settings: SupervisorSettings) -> str:
    raw = settings.python_executable.strip()
    candidate = Path(raw)
    if candidate.is_absolute():
        return str(candidate)
    project_candidate = settings.project_dir / candidate
    if project_candidate.exists() or any(separator in raw for separator in ("\\", "/")):
        return str(project_candidate.resolve())
    return raw


def _update_operation_state(
    settings: SupervisorSettings,
    operation_id: str,
    *,
    status: str,
    result: dict[str, object] | None = None,
    error: str | None = None,
) -> None:
    store = JsonStateStore(settings.runtime_dir / "state.json")
    payload = store.load()
    raw_history = payload.get("operation_history", [])
    history = [dict(item) for item in raw_history if isinstance(item, dict)] if isinstance(raw_history, list) else []
    target = next((item for item in reversed(history) if str(item.get("id")) == operation_id), None)
    if target is None:
        target = {
            "id": operation_id,
            "kind": "supervisor-bootstrap",
            "created_at": datetime.now().astimezone().isoformat(),
            "message": "Bootstrap operation",
            "result": {},
            "error": None,
        }
        history.append(target)
    target["status"] = status
    if status == "running":
        target["started_at"] = datetime.now().astimezone().isoformat()
    if status in {"success", "error"}:
        target["finished_at"] = datetime.now().astimezone().isoformat()
    if result is not None:
        target["result"] = result
    if error is not None:
        target["error"] = error[-10_000:]
    payload["operation_history"] = history[-50:]
    store.save(payload)


def _health_url(settings: SupervisorSettings) -> str:
    host = settings.host.strip().casefold()
    if host in {"0.0.0.0", "::", "[::]"}:
        host = "127.0.0.1"
    elif host == "localhost":
        host = "127.0.0.1"
    return f"http://{host}:{settings.port}/health"


def _wait_for_supervisor(settings: SupervisorSettings) -> None:
    deadline = time.monotonic() + max(20, settings.startup_grace_seconds + 20)
    last_error = "health endpoint did not answer"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(_health_url(settings), timeout=3) as response:
                if 200 <= int(response.status) < 300:
                    return
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = str(error)
        time.sleep(1.0)
    raise RuntimeError(f"Новый Supervisor не прошёл healthcheck: {last_error}")


'''
    source = replace_once(source, marker, helpers + marker, "bootstrap helpers")
    source = replace_once(
        source,
        "    command = (\n"
        "        settings.python_executable,\n",
        "    command = (\n"
        "        _resolved_python(settings),\n",
        "absolute bootstrap python",
    )
    source = replace_once(
        source,
        "    _run(create, cwd=settings.project_dir, timeout=30)\n"
        "    try:\n"
        "        _run(\n"
        "            (\"schtasks.exe\", \"/Run\", \"/TN\", bootstrap_task),\n"
        "            cwd=settings.project_dir,\n"
        "            timeout=30,\n"
        "        )\n"
        "    except Exception:\n"
        "        _delete_task(bootstrap_task, cwd=settings.project_dir)\n"
        "        raise\n",
        "    _acquire_lock(settings, operation_id)\n"
        "    try:\n"
        "        _run(create, cwd=settings.project_dir, timeout=30)\n"
        "        _run(\n"
        "            (\"schtasks.exe\", \"/Run\", \"/TN\", bootstrap_task),\n"
        "            cwd=settings.project_dir,\n"
        "            timeout=30,\n"
        "        )\n"
        "    except Exception:\n"
        "        _delete_task(bootstrap_task, cwd=settings.project_dir)\n"
        "        _release_lock(settings)\n"
        "        raise\n",
        "bootstrap lock launch",
    )
    source = replace_once(
        source,
        "    _write_result(settings, payload)\n"
        "    time.sleep(3.0)\n\n"
        "    try:\n",
        "    _write_result(settings, payload)\n"
        "    _update_operation_state(settings, operation_id, status=\"running\")\n"
        "    time.sleep(6.0)\n\n"
        "    try:\n",
        "bootstrap running state",
    )
    source = replace_once(
        source,
        "        _run_task(main_task, cwd=settings.project_dir)\n"
        "        payload.update(\n",
        "        _run_task(main_task, cwd=settings.project_dir)\n"
        "        _wait_for_supervisor(settings)\n"
        "        payload.update(\n",
        "success healthcheck",
    )
    source = replace_once(
        source,
        "        _write_result(settings, payload)\n"
        "        notifier.send(\n"
        "            \"Velvet Supervisor перезапущен\" if action == \"restart\" else \"Velvet Supervisor обновлён и перезапущен\",\n",
        "        _write_result(settings, payload)\n"
        "        _update_operation_state(\n"
        "            settings, operation_id, status=\"success\", result=dict(payload)\n"
        "        )\n"
        "        notifier.send(\n"
        "            \"Velvet Supervisor перезапущен\" if action == \"restart\" else \"Velvet Supervisor обновлён и перезапущен\",\n",
        "success operation state",
    )
    source = replace_once(
        source,
        "        try:\n"
        "            _run_task(main_task, cwd=settings.project_dir)\n"
        "        except Exception as restart_error:\n"
        "            payload[\"restart_error\"] = str(restart_error)[-5000:]\n"
        "            _write_result(settings, payload)\n",
        "        try:\n"
        "            _run_task(main_task, cwd=settings.project_dir)\n"
        "            _wait_for_supervisor(settings)\n"
        "            payload[\"recovered\"] = True\n"
        "        except Exception as restart_error:\n"
        "            payload[\"restart_error\"] = str(restart_error)[-5000:]\n"
        "        _write_result(settings, payload)\n"
        "        _update_operation_state(\n"
        "            settings,\n"
        "            operation_id,\n"
        "            status=\"error\",\n"
        "            result=dict(payload),\n"
        "            error=str(error),\n"
        "        )\n",
        "error recovery state",
    )
    source = replace_once(
        source,
        "    finally:\n"
        "        _delete_task(bootstrap_task, cwd=settings.project_dir)\n",
        "    finally:\n"
        "        _delete_task(bootstrap_task, cwd=settings.project_dir)\n"
        "        _release_lock(settings)\n",
        "bootstrap lock release",
    )
    ast.parse(source, filename=str(BOOTSTRAP))
    BOOTSTRAP.write_text(source, encoding="utf-8")


def patch_tests() -> None:
    source = TESTS.read_text(encoding="utf-8")
    source = replace_once(
        source,
        '        settings = SimpleNamespace(\n'
        '            python_executable=r"E:\\\\python\\\\main\\\\velevt\\\\.venv\\\\Scripts\\\\python.exe",\n'
        '            project_dir=Path(r"E:\\\\python\\\\main\\\\velevt"),\n'
        '        )\n',
        '        settings = SimpleNamespace(\n'
        '            python_executable=r".venv\\\\Scripts\\\\python.exe",\n'
        '            project_dir=Path(r"E:\\\\python\\\\main\\\\velevt"),\n'
        '            runtime_dir=Path(r"E:\\\\python\\\\main\\\\velevt\\\\runtime\\\\supervisor"),\n'
        '        )\n',
        "relative python test fixture",
    )
    source = replace_once(
        source,
        '        with patch("velvet_supervisor.bootstrap.os.name", "nt"), patch(\n'
        '            "velvet_supervisor.bootstrap._run", side_effect=fake_run\n'
        '        ), patch.dict(os.environ, {"SUPERVISOR_TASK_NAME": "VelvetSupervisor"}, clear=False):\n',
        '        with patch("velvet_supervisor.bootstrap.os.name", "nt"), patch(\n'
        '            "velvet_supervisor.bootstrap._run", side_effect=fake_run\n'
        '        ), patch(\n'
        '            "velvet_supervisor.bootstrap._acquire_lock"\n'
        '        ) as acquire_lock, patch(\n'
        '            "velvet_supervisor.bootstrap._release_lock"\n'
        '        ), patch.dict(os.environ, {"SUPERVISOR_TASK_NAME": "VelvetSupervisor"}, clear=False):\n',
        "bootstrap lock mocks",
    )
    source = replace_once(
        source,
        '        self.assertEqual("update", launch.action)\n'
        '        self.assertEqual(2, len(calls))\n',
        '        self.assertEqual("update", launch.action)\n'
        '        acquire_lock.assert_called_once_with(settings, "abc123def456")\n'
        '        self.assertEqual(2, len(calls))\n',
        "lock assertion",
    )
    source = replace_once(
        source,
        '        action_text = create[create.index("/TR") + 1]\n'
        '        self.assertIn("velvet_supervisor.bootstrap", action_text)\n',
        '        action_text = create[create.index("/TR") + 1]\n'
        '        self.assertIn(str(settings.project_dir), action_text)\n'
        '        self.assertIn("velvet_supervisor.bootstrap", action_text)\n',
        "absolute path assertion",
    )
    ast.parse(source, filename=str(TESTS))
    TESTS.write_text(source, encoding="utf-8")


def main() -> None:
    patch_bootstrap()
    patch_tests()


if __name__ == "__main__":
    main()
