#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any

_MAX_RESPONSE_BYTES = 2_500_000


class LauncherClientError(RuntimeError):
    pass


class SandboxLauncherClient:
    def __init__(self, socket_path: str | None = None) -> None:
        raw = socket_path or os.environ.get(
            "HERMES_SANDBOX_LAUNCHER_SOCKET",
            "/run/hermes-sandbox/launcher.sock",
        )
        self.socket_path = Path(raw)
        if not self.socket_path.is_absolute():
            raise RuntimeError("HERMES_SANDBOX_LAUNCHER_SOCKET должен быть absolute path")

    def _request(self, payload: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        ) + b"\n"
        if len(body) > 131_072:
            raise LauncherClientError("launcher request exceeds 128 KiB")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(timeout_seconds)
                client.connect(str(self.socket_path))
                client.sendall(body)
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = client.recv(65_536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > _MAX_RESPONSE_BYTES:
                        raise LauncherClientError("launcher response exceeds limit")
                    if b"\n" in chunk:
                        break
        except (OSError, socket.timeout) as error:
            raise LauncherClientError(
                f"sandbox launcher unavailable: {type(error).__name__}"
            ) from error
        raw = b"".join(chunks).split(b"\n", 1)[0]
        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise LauncherClientError("sandbox launcher returned invalid JSON") from error
        if not isinstance(response, dict):
            raise LauncherClientError("sandbox launcher response must be an object")
        if response.get("ok") is not True:
            message = str(response.get("error") or "sandbox launcher rejected request")
            raise LauncherClientError(message[:2_000])
        return response

    def ping(self) -> dict[str, Any]:
        return self._request({"action": "ping"}, timeout_seconds=5)

    def run(
        self,
        *,
        run_id: str,
        project: str,
        workspace: Path,
        model: str,
        route: str,
        mutation_policy: str,
        timeout_seconds: int,
        prompt: str,
    ) -> dict[str, Any]:
        response = self._request(
            {
                "action": "run",
                "run_id": run_id,
                "project": project,
                "workspace": str(workspace),
                "model": model,
                "route": route,
                "mutation_policy": mutation_policy,
                "timeout_seconds": timeout_seconds,
                "prompt": prompt,
            },
            timeout_seconds=timeout_seconds + 60,
        )
        result = response.get("result")
        if not isinstance(result, dict):
            raise LauncherClientError("sandbox launcher result is missing")
        expected = {"returncode", "stdout", "stderr", "cancelled", "execution_started"}
        if set(result) != expected:
            raise LauncherClientError("sandbox launcher result schema mismatch")
        if not isinstance(result["returncode"], int):
            raise LauncherClientError("sandbox launcher returncode is invalid")
        if not isinstance(result["stdout"], str) or not isinstance(result["stderr"], str):
            raise LauncherClientError("sandbox launcher output is invalid")
        if not isinstance(result["cancelled"], bool):
            raise LauncherClientError("sandbox launcher cancelled flag is invalid")
        if not isinstance(result["execution_started"], bool):
            raise LauncherClientError("sandbox launcher execution flag is invalid")
        return result

    def probe(self, project: str) -> dict[str, Any]:
        response = self._request(
            {"action": "probe", "project": project},
            timeout_seconds=60,
        )
        result = response.get("result")
        if not isinstance(result, dict) or result.get("returncode") != 0:
            raise LauncherClientError("sandbox launcher probe failed")
        return result

    def cancel(self, run_id: str) -> bool:
        response = self._request(
            {"action": "cancel", "run_id": run_id},
            timeout_seconds=20,
        )
        return bool(response.get("cancelled"))
