from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "deploy/hermes-coders/codex_runner.py"
README = ROOT / "deploy/hermes-coders/README.md"
TEST = ROOT / "tests/test_codex_runner_rate_limits.py"
WORKLOG = ROOT / "docs/worklog/2026-08-06-codex-rate-limit-probe.md"

NEW_RATE_LIMIT_BLOCK = r'''def _normalize_codex_rate_window(value: object) -> dict[str, int | float | None] | None:
    if not isinstance(value, dict):
        return None
    used_percent = _bounded_number(
        value.get("usedPercent"),
        minimum=0,
        maximum=100,
    )
    duration = _bounded_number(
        value.get("windowDurationMins"),
        minimum=1,
        maximum=525_600,
    )
    if used_percent is None or duration is None:
        return None
    resets_at = _bounded_number(
        value.get("resetsAt"),
        minimum=1,
        maximum=32_503_680_000,
    )
    return {
        "used_percent": used_percent,
        "window_duration_mins": int(duration),
        "resets_at": int(resets_at) if resets_at is not None else None,
    }


def _classify_codex_rate_windows(
    *values: dict[str, int | float | None] | None,
) -> tuple[
    dict[str, int | float | None] | None,
    dict[str, int | float | None] | None,
]:
    """Map provider buckets to the stable short/long UI contract.

    Codex has changed whether its weekly bucket is called ``primary`` or
    ``secondary``. Duration is the reliable semantic signal: sub-day windows
    are short, while a lone day-or-longer window belongs in the long slot.
    """
    windows = [dict(value) for value in values if value is not None]
    if not windows:
        return None, None
    windows.sort(key=lambda item: int(item["window_duration_mins"] or 0))
    if len(windows) == 1:
        only = windows[0]
        if int(only["window_duration_mins"] or 0) >= 24 * 60:
            return None, only
        return only, None
    return windows[0], windows[-1]


def normalize_codex_subscription_rate_limits(
    account_result: object,
    rate_result: object,
) -> dict[str, Any]:
    if not isinstance(account_result, dict):
        raise RuntimeError("Codex вернул неизвестный формат аккаунта")
    account = account_result.get("account")
    if not isinstance(account, dict) or account.get("type") != "chatgpt":
        raise RuntimeError("Codex не авторизован через ChatGPT")
    plan_type = str(account.get("planType") or "unknown").strip().casefold()
    if not isinstance(rate_result, dict):
        raise RuntimeError("Codex вернул неизвестный формат лимитов")
    rate_limits = rate_result.get("rateLimits")
    if not isinstance(rate_limits, dict):
        raise RuntimeError("Codex не вернул лимиты подписки")
    primary, secondary = _classify_codex_rate_windows(
        _normalize_codex_rate_window(rate_limits.get("primary")),
        _normalize_codex_rate_window(rate_limits.get("secondary")),
    )
    if primary is None and secondary is None:
        raise RuntimeError("Codex не вернул окна лимитов подписки")
    reached = rate_limits.get("rateLimitReachedType")
    return {
        "plan_type": plan_type,
        "primary": primary,
        "secondary": secondary,
        "rate_limit_reached_type": reached if isinstance(reached, str) else None,
    }


def _app_server_stderr(stderr_tail: bytearray) -> str:
    details = stderr_tail.decode("utf-8", errors="replace").strip()
    return redact_text(details[-2_000:])


def _app_server_error(payload: object, *, request_name: str) -> str:
    if isinstance(payload, dict):
        code = payload.get("code")
        message = redact_text(str(payload.get("message") or "неизвестная ошибка"))
        suffix = f" ({code})" if code is not None else ""
        return f"Codex app-server {request_name} отклонил запрос{suffix}: {message}"
    return f"Codex app-server {request_name} отклонил запрос"


def _read_codex_subscription_rate_limits_once(
    codex_bin: str,
    codex_home: Path,
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    try:
        process = subprocess.Popen(
            [codex_bin, "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            bufsize=0,
            env={**os.environ, "CODEX_HOME": str(codex_home)},
        )
    except OSError as error:
        raise RuntimeError("Codex app-server не запустился") from error
    if process.stdin is None or process.stdout is None or process.stderr is None:
        process.kill()
        raise RuntimeError("Codex app-server не запустился")

    deadline = time.monotonic() + max(3, timeout_seconds)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    stdout_buffer = bytearray()
    stderr_tail = bytearray()
    request_names = {
        1: "initialize",
        2: "account/read",
        3: "account/rateLimits/read",
    }

    def send(payload: dict[str, Any]) -> None:
        process.stdin.write(
            json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        )
        process.stdin.flush()

    def drain(
        expected_ids: set[int],
        results: dict[int, object],
    ) -> None:
        while True:
            separator = stdout_buffer.find(b"\n")
            if separator < 0:
                return
            raw = bytes(stdout_buffer[:separator]).strip()
            del stdout_buffer[: separator + 1]
            if not raw:
                continue
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            request_id = payload.get("id")
            if request_id not in expected_ids:
                continue
            numeric_id = int(request_id)
            error = payload.get("error")
            if error is not None:
                raise RuntimeError(
                    _app_server_error(
                        error,
                        request_name=request_names.get(numeric_id, str(numeric_id)),
                    )
                )
            results[numeric_id] = payload.get("result")

    def collect(expected_ids: set[int]) -> dict[int, object]:
        results: dict[int, object] = {}
        while expected_ids - set(results):
            drain(expected_ids, results)
            if not expected_ids - set(results):
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                details = _app_server_stderr(stderr_tail)
                suffix = f": {details}" if details else ""
                raise RuntimeError(
                    "Codex app-server превысил время ожидания" + suffix
                )
            events = selector.select(remaining)
            if not events:
                details = _app_server_stderr(stderr_tail)
                suffix = f": {details}" if details else ""
                raise RuntimeError(
                    "Codex app-server превысил время ожидания" + suffix
                )
            for key, _ in events:
                stream = key.fileobj
                try:
                    chunk = os.read(stream.fileno(), 65_536)
                except OSError as error:
                    raise RuntimeError("Codex app-server недоступен") from error
                if not chunk:
                    try:
                        selector.unregister(stream)
                    except KeyError:
                        pass
                    if key.data == "stdout":
                        if stdout_buffer:
                            stdout_buffer.extend(b"\n")
                        drain(expected_ids, results)
                        if expected_ids - set(results):
                            details = _app_server_stderr(stderr_tail)
                            suffix = f": {details}" if details else ""
                            raise RuntimeError(
                                "Codex app-server завершился без ответа" + suffix
                            )
                    continue
                if key.data == "stdout":
                    stdout_buffer.extend(chunk)
                else:
                    stderr_tail.extend(chunk)
                    if len(stderr_tail) > 16_384:
                        del stderr_tail[:-16_384]
        return results

    try:
        send(
            {
                "method": "initialize",
                "id": 1,
                "params": {
                    "clientInfo": {
                        "name": "velvet_balance_probe",
                        "title": "Velvet Balance Probe",
                        "version": "1.0",
                    }
                },
            }
        )
        collect({1})
        send({"method": "initialized", "params": {}})
        send(
            {
                "method": "account/read",
                "id": 2,
                "params": {"refreshToken": False},
            }
        )
        send({"method": "account/rateLimits/read", "id": 3})
        results = collect({2, 3})
        return normalize_codex_subscription_rate_limits(results[2], results[3])
    except (BrokenPipeError, OSError, ValueError) as error:
        raise RuntimeError("Codex app-server недоступен") from error
    finally:
        selector.close()
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                stream.close()
            except OSError:
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


def read_codex_subscription_rate_limits(
    codex_bin: str,
    codex_home: Path,
    *,
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    if not (codex_home / "auth.json").is_file():
        raise RuntimeError("Codex не авторизован")
    last_error: RuntimeError | None = None
    for attempt in range(2):
        try:
            return _read_codex_subscription_rate_limits_once(
                codex_bin,
                codex_home,
                timeout_seconds=timeout_seconds,
            )
        except RuntimeError as error:
            last_error = error
            if attempt == 0:
                time.sleep(0.25)
    assert last_error is not None
    raise last_error
'''

TEST_CONTENT = r'''from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import textwrap
import unittest
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "codex_runner_rate_limit_test_module",
    ROOT / "deploy/hermes-coders/codex_runner.py",
)
assert SPEC and SPEC.loader
codex_runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = codex_runner
SPEC.loader.exec_module(codex_runner)


_FAKE_CODEX = r'''#!/usr/bin/env python3
import json
import os
import sys

mode = os.environ.get("FAKE_CODEX_MODE", "success")
account = {
    "id": 2,
    "result": {
        "account": {
            "type": "chatgpt",
            "planType": "plus",
        }
    },
}
weekly = {
    "id": 3,
    "result": {
        "rateLimits": {
            "primary": {
                "usedPercent": 31,
                "windowDurationMins": 10080,
                "resetsAt": 1800000000,
            },
            "secondary": None,
            "rateLimitReachedType": None,
        }
    },
}
failure = {
    "id": 3,
    "error": {
        "code": -32001,
        "message": "backend unavailable Authorization: Bearer abcdefghijklmnop",
    },
}

for raw in sys.stdin.buffer:
    request = json.loads(raw)
    request_id = request.get("id")
    if request_id == 1:
        os.write(
            sys.stdout.fileno(),
            (json.dumps({"id": 1, "result": {}}) + "\n").encode(),
        )
    elif request_id == 3:
        second = failure if mode == "error" else weekly
        payload = json.dumps(account) + "\n" + json.dumps(second) + "\n"
        os.write(sys.stdout.fileno(), payload.encode())
'''


class CodexRateLimitProbeTests(unittest.TestCase):
    def _fake_codex(self, root: Path) -> Path:
        executable = root / "codex"
        executable.write_text(textwrap.dedent(_FAKE_CODEX), encoding="utf-8")
        executable.chmod(0o755)
        return executable

    def test_reads_two_responses_written_in_one_stdout_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            home.mkdir()
            (home / "auth.json").write_text("{}", encoding="utf-8")
            result = codex_runner.read_codex_subscription_rate_limits(
                str(self._fake_codex(root)),
                home,
                timeout_seconds=2,
            )
        self.assertEqual("plus", result["plan_type"])
        self.assertIsNone(result["primary"])
        self.assertEqual(10080, result["secondary"]["window_duration_mins"])
        self.assertEqual(31.0, result["secondary"]["used_percent"])

    def test_classifies_windows_by_duration_instead_of_provider_slot(self) -> None:
        result = codex_runner.normalize_codex_subscription_rate_limits(
            {"account": {"type": "chatgpt", "planType": "plus"}},
            {
                "rateLimits": {
                    "primary": {
                        "usedPercent": 40,
                        "windowDurationMins": 10080,
                    },
                    "secondary": {
                        "usedPercent": 20,
                        "windowDurationMins": 300,
                    },
                }
            },
        )
        self.assertEqual(300, result["primary"]["window_duration_mins"])
        self.assertEqual(10080, result["secondary"]["window_duration_mins"])

    def test_surfaces_sanitized_json_rpc_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            home.mkdir()
            (home / "auth.json").write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {"FAKE_CODEX_MODE": "error"}):
                with self.assertRaisesRegex(RuntimeError, "backend unavailable") as raised:
                    codex_runner.read_codex_subscription_rate_limits(
                        str(self._fake_codex(root)),
                        home,
                        timeout_seconds=2,
                    )
        self.assertNotIn("abcdefghijklmnop", str(raised.exception))
        self.assertIn("[REDACTED]", str(raised.exception))

    def test_manager_maps_probe_failure_to_bad_gateway(self) -> None:
        manager = codex_runner.CodexManager.__new__(codex_runner.CodexManager)
        manager.codex_bin = "codex"
        manager.codex_home = Path("/tmp/codex-test")
        with patch.object(
            codex_runner,
            "read_codex_subscription_rate_limits",
            side_effect=RuntimeError("probe failed"),
        ):
            with self.assertRaises(codex_runner.RunnerError) as raised:
                manager.rate_limits()
        self.assertEqual(HTTPStatus.BAD_GATEWAY, raised.exception.status)
        self.assertEqual("probe failed", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
'''

WORKLOG_CONTENT = '''# Codex rate-limit probe repair

Date: 2026-08-06

## Incident

`GET /v1/rate-limits` returned HTTP 500 from the internal Codex runner. The
orchestration router surfaced that as HTTP 502 with only
`Internal runner error: RuntimeError`, while GPT Image 2 generation itself
continued to work.

## Root cause

The probe combined `selectors` with a buffered text-mode `stdout.readline()`.
When Codex app-server emitted the `account/read` and `account/rateLimits/read`
responses in one write, `readline()` could prefetch both lines. The second line
then lived in Python's userspace buffer while `select()` waited for new kernel
readability until timeout.

The probe also trusted provider names `primary` and `secondary` as UI semantics.
Codex can expose only a long weekly bucket in `primary`, which would otherwise
be shown as the short window.

## Change

- use unbuffered binary pipes and an explicit JSONL byte buffer;
- drain all complete buffered lines before waiting on the selector;
- drain and redact app-server stderr;
- preserve sanitized JSON-RPC error details;
- retry the bounded read once for transient app-server failures;
- classify short and long windows by duration;
- map probe failures to a meaningful HTTP 502 RunnerError;
- add a fake app-server regression that writes both responses in one chunk.

## Verification

- `python -m unittest tests.test_codex_runner_rate_limits`
- `python -m compileall -q deploy/hermes-coders/codex_runner.py tests/test_codex_runner_rate_limits.py`
'''

README_SECTION = '''

## Codex subscription rate-limit probe

The coder runner reads ChatGPT subscription windows through Codex app-server
JSONL over stdio. The reader uses unbuffered binary pipes and drains every
complete response already held in its byte buffer before waiting for more I/O.
This prevents a second response from being stranded in a text wrapper buffer.

Provider bucket names are not treated as presentation semantics. Windows are
ordered by `windowDurationMins`: the shortest bucket is exposed as `primary`
(the short window), and the longest as `secondary` (the long or weekly window).
When Codex returns only a day-or-longer bucket, `primary` remains null and that
bucket is exposed as `secondary`.

A failed probe is retried once. Persistent failures return HTTP 502 with a
sanitized app-server reason; secrets and authorization material remain redacted.
'''


def patch_runner() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    start = source.index("def _normalize_codex_rate_window")
    end = source.index("\n\n\nclass RunStore:", start)
    source = source[:start] + NEW_RATE_LIMIT_BLOCK + source[end:]
    old_method = '''    def rate_limits(self) -> dict[str, Any]:
        return read_codex_subscription_rate_limits(
            self.codex_bin,
            self.codex_home,
        )
'''
    new_method = '''    def rate_limits(self) -> dict[str, Any]:
        try:
            return read_codex_subscription_rate_limits(
                self.codex_bin,
                self.codex_home,
            )
        except RuntimeError as error:
            raise RunnerError(
                HTTPStatus.BAD_GATEWAY,
                redact_text(str(error)),
            ) from error
'''
    if old_method not in source:
        raise RuntimeError("CodexManager.rate_limits block changed")
    source = source.replace(old_method, new_method, 1)
    RUNNER.write_text(source, encoding="utf-8")


def patch_docs() -> None:
    readme = README.read_text(encoding="utf-8")
    marker = "## Codex subscription rate-limit probe"
    if marker not in readme:
        README.write_text(readme.rstrip() + README_SECTION + "\n", encoding="utf-8")
    WORKLOG.parent.mkdir(parents=True, exist_ok=True)
    WORKLOG.write_text(WORKLOG_CONTENT, encoding="utf-8")


def main() -> int:
    patch_runner()
    patch_docs()
    TEST.write_text(TEST_CONTENT, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
