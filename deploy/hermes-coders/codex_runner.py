#!/usr/bin/env python3
from __future__ import annotations

import hmac
import json
import math
import os
import re
import selectors
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_MAX_BODY_BYTES = 65_536
_RUN_ID = re.compile(r"^[a-f0-9]{32}$")
_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
_DEFAULT_MODELS = ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol")
_SECRET_KEY = re.compile(r"(?i)(token|secret|password|api[_-]?key|authorization)")
_SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(
        r"(?i)([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY)[A-Z0-9_]*\s*[=:]\s*)[^\s,;]+"
    ),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|github_pat_[A-Za-z0-9_]+|gh[opsu]_[A-Za-z0-9]+)\b"),
)
_RETRYABLE_MODEL_ERRORS = re.compile(
    r"(?i)(rate.?limit|usage.?limit|allowance|capacity|temporar(?:y|ily).?unavailable|"
    r"model.{0,40}(?:unavailable|not available|not found|disabled)|too many requests|429)"
)


class RunnerError(RuntimeError):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_text(value: str) -> str:
    result = value
    for pattern in _SECRET_TEXT_PATTERNS:
        replacement = r"\1[REDACTED]" if pattern.groups else "[REDACTED]"
        result = pattern.sub(replacement, result)
    return result


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def parse_models(value: str | None) -> tuple[str, ...]:
    raw = value or ",".join(_DEFAULT_MODELS)
    result = tuple(dict.fromkeys(item.strip() for item in raw.split(",") if item.strip()))
    if not result:
        raise RuntimeError("CODEX_ALLOWED_MODELS не содержит моделей")
    invalid = [model for model in result if model not in _DEFAULT_MODELS]
    if invalid:
        raise RuntimeError("Запрещённые CODEX models: " + ", ".join(invalid))
    return result


def fallback_order(selected: str, allowed: tuple[str, ...]) -> tuple[str, ...]:
    preferred = {
        "gpt-5.6-luna": ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"),
        "gpt-5.6-terra": ("gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna"),
        "gpt-5.6-sol": ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"),
    }[selected]
    return tuple(model for model in preferred if model in allowed)


def _walk_text(value: Any, *, key: str = "") -> list[str]:
    result: list[str] = []
    if isinstance(value, dict):
        for child_key, child in value.items():
            result.extend(_walk_text(child, key=str(child_key)))
    elif isinstance(value, list):
        for child in value:
            result.extend(_walk_text(child, key=key))
    elif isinstance(value, str) and key.casefold() in {
        "text",
        "output_text",
        "final_response",
        "message",
        "content",
    }:
        clean = value.strip()
        if clean:
            result.append(clean)
    return result


def parse_jsonl_output(stdout: str) -> tuple[str, dict[str, int] | None, Any | None]:
    events: list[Any] = []
    usage: dict[str, int] = {}
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(event)
        stack = [event]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                for key, value in item.items():
                    normalized = str(key).casefold()
                    if normalized in {
                        "input_tokens",
                        "output_tokens",
                        "cached_input_tokens",
                        "total_tokens",
                    } and isinstance(value, int):
                        usage[normalized] = max(usage.get(normalized, 0), value)
                    else:
                        stack.append(value)
            elif isinstance(item, list):
                stack.extend(item)
    candidates: list[str] = []
    for event in events:
        candidates.extend(_walk_text(event))
    output = candidates[-1] if candidates else stdout.strip()[-12_000:]
    return redact_text(output), (usage or None), redact(events[-1]) if events else None


def parse_structured_output(output: str) -> dict[str, Any]:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as error:
        raise ValueError("Codex output не является schema-bound JSON") from error
    expected = {"status", "branch", "pr", "tests", "blocker", "memory_candidates"}
    if not isinstance(payload, dict) or set(payload) != expected:
        raise ValueError("Codex output содержит неверный набор полей")
    if payload.get("status") not in {"completed", "blocked", "failed"}:
        raise ValueError("Codex output содержит неверный status")
    for key in ("branch", "pr", "blocker"):
        if not isinstance(payload.get(key), str):
            raise ValueError(f"Codex output field {key} должен быть строкой")
    tests = payload.get("tests")
    if not isinstance(tests, list) or not all(isinstance(item, str) for item in tests):
        raise ValueError("Codex output tests должен быть списком строк")
    candidates = payload.get("memory_candidates")
    if not isinstance(candidates, list) or not all(
        isinstance(item, dict) for item in candidates
    ):
        raise ValueError("Codex output memory_candidates должен быть списком objects")
    return redact(payload)


def render_legacy_output(payload: dict[str, Any]) -> str:
    tests = payload.get("tests") or []
    return "\n".join(
        (
            f"STATUS: {payload['status']}",
            f"BRANCH: {payload['branch'] or 'none'}",
            f"PR: {payload['pr'] or 'none'}",
            f"TESTS: {'; '.join(str(item) for item in tests) or 'none'}",
            f"BLOCKER: {payload['blocker'] or 'none'}",
        )
    )


def _bounded_number(
    value: object,
    *,
    minimum: float,
    maximum: float,
) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or result < minimum or result > maximum:
        return None
    return result


def _normalize_codex_rate_window(value: object) -> dict[str, int | float | None] | None:
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



class RunStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, run_id: str) -> Path:
        return self.root / f"{run_id}.json"

    def write(self, record: dict[str, Any]) -> None:
        run_id = str(record.get("run_id", ""))
        if not _RUN_ID.fullmatch(run_id):
            raise RunnerError(HTTPStatus.INTERNAL_SERVER_ERROR, "Некорректный run_id")
        payload = json.dumps(redact(record), ensure_ascii=False, indent=2) + "\n"
        with self._lock:
            fd, temp_name = tempfile.mkstemp(prefix=f".{run_id}.", dir=self.root, text=True)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(temp_name, 0o600)
                os.replace(temp_name, self._path(run_id))
            finally:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass

    def read(self, run_id: str) -> dict[str, Any]:
        if not _RUN_ID.fullmatch(run_id):
            raise RunnerError(HTTPStatus.BAD_REQUEST, "Некорректный run_id")
        try:
            payload = json.loads(self._path(run_id).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RunnerError(HTTPStatus.NOT_FOUND, "Run не найден") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise RunnerError(HTTPStatus.INTERNAL_SERVER_ERROR, "Журнал run повреждён") from exc
        if not isinstance(payload, dict):
            raise RunnerError(HTTPStatus.INTERNAL_SERVER_ERROR, "Журнал run имеет неверный формат")
        return payload

    def update(self, run_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            record = self.read(run_id)
            record.update(changes)
            record["updated_at"] = utc_now()
            self.write(record)
            return record


class CodexManager:
    def __init__(self) -> None:
        self.api_key = os.environ.get("CODEX_RUNNER_API_KEY", "").strip()
        if len(self.api_key) < 24:
            raise RuntimeError("CODEX_RUNNER_API_KEY отсутствует или короче 24 символов")
        self.codex_bin = os.environ.get("CODEX_BIN", "codex").strip() or "codex"
        self.codex_home = Path(os.environ.get("CODEX_HOME", "/opt/codex")).resolve()
        self.output_schema = (self.codex_home / "output.schema.json").resolve()
        if self.output_schema.parent != self.codex_home or not self.output_schema.is_file():
            raise RuntimeError("CODEX_HOME не содержит output.schema.json")
        try:
            schema = json.loads(self.output_schema.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("Codex output schema повреждена") from error
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise RuntimeError("Codex output schema имеет неверный формат")
        self.workspace = Path(os.environ.get("CODEX_WORKSPACE", "/workspace")).resolve()
        self.allowed_models = parse_models(os.environ.get("CODEX_ALLOWED_MODELS"))
        self.default_model = os.environ.get("CODEX_DEFAULT_MODEL", "gpt-5.6-terra").strip()
        if self.default_model not in self.allowed_models:
            raise RuntimeError("CODEX_DEFAULT_MODEL отсутствует в CODEX_ALLOWED_MODELS")
        self.timeout_seconds = max(60, int(os.environ.get("CODEX_RUN_TIMEOUT_SECONDS", "7200")))
        self.store = RunStore(Path(os.environ.get("CODEX_RUN_ROOT", "/opt/codex-runs")))
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._process_lock = threading.RLock()
        self._execution_lock = threading.Lock()

    def authenticate(self, authorization: str | None) -> None:
        prefix = "Bearer "
        if not authorization or not authorization.startswith(prefix):
            raise RunnerError(HTTPStatus.UNAUTHORIZED, "Требуется Bearer token")
        candidate = authorization[len(prefix) :].strip()
        if not hmac.compare_digest(candidate, self.api_key):
            raise RunnerError(HTTPStatus.FORBIDDEN, "Неверный Bearer token")

    def capabilities(self) -> dict[str, Any]:
        version = "unknown"
        try:
            result = subprocess.run(
                [self.codex_bin, "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
                env={**os.environ, "CODEX_HOME": str(self.codex_home)},
            )
            version = (result.stdout or result.stderr).strip()[:200] or "unknown"
        except (OSError, subprocess.TimeoutExpired):
            pass
        return {
            "provider": "openai-codex-cli",
            "version": redact_text(version),
            "authenticated": (self.codex_home / "auth.json").is_file(),
            "default_model": self.default_model,
            "models": list(self.allowed_models),
            "fallback": "model-capacity-only",
            "max_concurrency": 1,
            "workspace": str(self.workspace),
            "structured_output": True,
        }

    def rate_limits(self) -> dict[str, Any]:
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

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed_fields = {"input", "session_id", "instructions", "model"}
        if not set(payload).issubset(allowed_fields) or "input" not in payload:
            raise RunnerError(HTTPStatus.BAD_REQUEST, "Некорректный Runs API payload")
        prompt = payload.get("input")
        instructions = payload.get("instructions", "")
        session_id = payload.get("session_id")
        model = payload.get("model", self.default_model)
        if not isinstance(prompt, str) or not prompt.strip():
            raise RunnerError(HTTPStatus.BAD_REQUEST, "input должен быть непустой строкой")
        if len(prompt) > 30_000:
            raise RunnerError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "input превышает 30000 символов")
        if not isinstance(instructions, str) or len(instructions) > 8_000:
            raise RunnerError(HTTPStatus.BAD_REQUEST, "instructions имеет неверный формат")
        if session_id is not None and (not isinstance(session_id, str) or len(session_id) > 200):
            raise RunnerError(HTTPStatus.BAD_REQUEST, "session_id имеет неверный формат")
        if not isinstance(model, str) or model not in self.allowed_models:
            raise RunnerError(HTTPStatus.BAD_REQUEST, "Запрошена неподдерживаемая Codex model")
        if not self.workspace.is_dir() or not (self.workspace / ".git").exists():
            raise RunnerError(HTTPStatus.SERVICE_UNAVAILABLE, "CODEX_WORKSPACE не является Git checkout")
        if not (self.codex_home / "auth.json").is_file():
            raise RunnerError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Codex не авторизован; выполните codex login --device-auth",
            )

        run_id = uuid.uuid4().hex
        now = utc_now()
        record = {
            "run_id": run_id,
            "session_id": session_id,
            "status": "queued",
            "model": model,
            "attempted_models": [],
            "created_at": now,
            "updated_at": now,
            "last_event": {"type": "queued", "model": model},
        }
        self.store.write(record)
        thread = threading.Thread(
            target=self._execute,
            args=(run_id, prompt.strip(), instructions.strip(), model),
            name=f"codex-run-{run_id[:8]}",
            daemon=True,
        )
        thread.start()
        return record

    def status(self, run_id: str) -> dict[str, Any]:
        return self.store.read(run_id)

    def stop(self, run_id: str) -> dict[str, Any]:
        record = self.store.read(run_id)
        if str(record.get("status")) in _TERMINAL_STATUSES:
            return record
        self.store.update(run_id, stop_requested=True, last_event={"type": "stop_requested"})
        with self._process_lock:
            process = self._processes.get(run_id)
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        return self.store.read(run_id)

    def _execute(self, run_id: str, prompt: str, instructions: str, selected_model: str) -> None:
        with self._execution_lock:
            current = self.store.read(run_id)
            if current.get("stop_requested"):
                self.store.update(
                    run_id,
                    status="cancelled",
                    finished_at=utc_now(),
                    last_event={"type": "cancelled_before_start"},
                )
                return
            self.store.update(run_id, status="running", started_at=utc_now())
            combined_prompt = prompt if not instructions else f"{instructions}\n\n{prompt}"
            attempts: list[str] = []
            errors: list[str] = []
            for model in fallback_order(selected_model, self.allowed_models):
                attempts.append(model)
                self.store.update(
                    run_id,
                    model=model,
                    attempted_models=attempts,
                    last_event={"type": "model_started", "model": model},
                )
                result = self._run_once(run_id, model, combined_prompt)
                if result["cancelled"]:
                    self.store.update(
                        run_id,
                        status="cancelled",
                        finished_at=utc_now(),
                        attempted_models=attempts,
                        error="Run остановлен владельцем",
                        last_event={"type": "cancelled", "model": model},
                    )
                    return
                stdout = str(result["stdout"])
                stderr = str(result["stderr"])
                output, usage, last_event = parse_jsonl_output(stdout)
                if int(result["returncode"]) == 0:
                    try:
                        structured = parse_structured_output(output)
                    except ValueError as error:
                        self.store.update(
                            run_id,
                            status="failed",
                            finished_at=utc_now(),
                            model=model,
                            attempted_models=attempts,
                            error=str(error),
                            last_event={"type": "invalid_structured_output", "model": model},
                        )
                        return
                    self.store.update(
                        run_id,
                        status="completed",
                        finished_at=utc_now(),
                        model=model,
                        attempted_models=attempts,
                        output=render_legacy_output(structured),
                        structured_output=structured,
                        usage=usage,
                        last_event=last_event or {"type": "completed", "model": model},
                    )
                    return
                details = redact_text((stderr or stdout).strip()[-4_000:])
                errors.append(f"{model}: {details or 'Codex завершился с ошибкой'}")
                if not _RETRYABLE_MODEL_ERRORS.search(f"{stdout}\n{stderr}"):
                    break
            self.store.update(
                run_id,
                status="failed",
                finished_at=utc_now(),
                attempted_models=attempts,
                error="\n".join(errors)[-12_000:],
                last_event={"type": "failed", "models": attempts},
            )

    def _run_once(self, run_id: str, model: str, prompt: str) -> dict[str, Any]:
        command = [
            self.codex_bin,
            "exec",
            "--json",
            "--model",
            model,
            "--sandbox",
            "workspace-write",
            "--output-schema",
            str(self.output_schema),
            "-",
        ]
        env = {**os.environ, "CODEX_HOME": str(self.codex_home)}
        process = subprocess.Popen(
            command,
            cwd=self.workspace,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        with self._process_lock:
            self._processes[run_id] = process
        try:
            try:
                stdout, stderr = process.communicate(input=prompt, timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    stdout, stderr = process.communicate(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    stdout, stderr = process.communicate()
                stderr = (stderr or "") + "\nCodex run timed out"
            record = self.store.read(run_id)
            return {
                "returncode": process.returncode if process.returncode is not None else 1,
                "stdout": stdout or "",
                "stderr": stderr or "",
                "cancelled": bool(record.get("stop_requested")),
            }
        finally:
            with self._process_lock:
                self._processes.pop(run_id, None)


class Handler(BaseHTTPRequestHandler):
    server_version = "VelvetCodexRunner/1"

    @property
    def manager(self) -> CodexManager:
        return self.server.manager  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        print(redact_text(format % args), flush=True)

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(redact(payload), ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise RunnerError(HTTPStatus.BAD_REQUEST, "Некорректный Content-Length") from exc
        if not 0 <= length <= _MAX_BODY_BYTES:
            raise RunnerError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request body слишком большой")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RunnerError(HTTPStatus.BAD_REQUEST, "Некорректный JSON") from exc
        if not isinstance(payload, dict):
            raise RunnerError(HTTPStatus.BAD_REQUEST, "JSON body должен быть объектом")
        return payload

    def _run_id(self, suffix: str = "") -> str:
        path = urlparse(self.path).path
        pattern = rf"^/v1/runs/([a-f0-9]{{32}}){re.escape(suffix)}$"
        match = re.fullmatch(pattern, path)
        if not match:
            raise RunnerError(HTTPStatus.NOT_FOUND, "Маршрут не найден")
        return match.group(1)

    def _dispatch(self) -> None:
        path = urlparse(self.path).path
        if self.command == "GET" and path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok"})
            return
        self.manager.authenticate(self.headers.get("Authorization"))
        if self.command == "GET" and path == "/v1/capabilities":
            self._json(HTTPStatus.OK, self.manager.capabilities())
            return
        if self.command == "GET" and path == "/v1/rate-limits":
            self._json(HTTPStatus.OK, self.manager.rate_limits())
            return
        if self.command == "POST" and path == "/v1/runs":
            self._json(HTTPStatus.ACCEPTED, self.manager.submit(self._read_json()))
            return
        if self.command == "GET" and re.fullmatch(r"/v1/runs/[a-f0-9]{32}", path):
            self._json(HTTPStatus.OK, self.manager.status(self._run_id()))
            return
        if self.command == "POST" and re.fullmatch(r"/v1/runs/[a-f0-9]{32}/stop", path):
            self._read_json()
            self._json(HTTPStatus.OK, self.manager.stop(self._run_id("/stop")))
            return
        raise RunnerError(HTTPStatus.NOT_FOUND, "Маршрут не найден")

    def do_GET(self) -> None:  # noqa: N802
        self._handle()

    def do_POST(self) -> None:  # noqa: N802
        self._handle()

    def _handle(self) -> None:
        try:
            self._dispatch()
        except RunnerError as exc:
            self._json(exc.status, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover
            self._json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Internal runner error: {type(exc).__name__}"},
            )


def main() -> int:
    host = os.environ.get("CODEX_RUNNER_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.environ.get("CODEX_RUNNER_PORT", "8642"))
    if not 1024 <= port <= 65535:
        raise RuntimeError("CODEX_RUNNER_PORT должен быть от 1024 до 65535")
    manager = CodexManager()
    server = ThreadingHTTPServer((host, port), Handler)
    server.manager = manager  # type: ignore[attr-defined]
    print(
        f"Velvet Codex runner listening on {host}:{port}; "
        f"default={manager.default_model}; models={','.join(manager.allowed_models)}",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
