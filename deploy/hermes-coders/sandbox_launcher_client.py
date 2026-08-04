#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any

_MAX_RESPONSE_BYTES = 2_000_000


class LauncherClientError(RuntimeError):
    pass


class SandboxLauncherClient:
    def __init__(self, socket_path: str | None = None) -> None:
        self.socket_path = socket_path or os.environ.get(
            "HERMES_SANDBOX_LAUNCHER_SOCKET",
            "/run/hermes-sandbox/launcher.sock",
        )
        self.project = os.environ.get("HERMES_CODER_PROJECT", "").strip()
        self.project_token = os.environ.get(
            "HERMES_SANDBOX_LAUNCHER_TOKEN", ""
        ).strip()

    def _request(self, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        ) + b"\n"
        chunks: list[bytes] = []
        total = 0
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(timeout)
                client.connect(self.socket_path)
                client.sendall(body)
                while True:
                    chunk = client.recv(65_536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > _MAX_RESPONSE_BYTES:
                        raise LauncherClientError("launcher response exceeds 2 MB")
                    if b"\n" in chunk:
                        break
        except (OSError, TimeoutError) as error:
            raise LauncherClientError("sandbox launcher is unavailable") from error
        raw = b"".join(chunks).split(b"\n", 1)[0]
        if not raw:
            raise LauncherClientError("sandbox launcher returned an empty response")
        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise LauncherClientError("sandbox launcher returned invalid JSON") from error
        if not isinstance(response, dict):
            raise LauncherClientError("sandbox launcher response is not an object")
        if response.get("ok") is not True:
            raise LauncherClientError(str(response.get("error") or "launcher rejected request"))
        return response

    def _project_credentials(self, project: str | None = None) -> tuple[str, str]:
        selected = project or self.project
        if selected not in {"velvet", "max"}:
            raise LauncherClientError("sandbox launcher project is unavailable")
        if self.project and selected != self.project:
            raise LauncherClientError("cross-project launcher request is forbidden")
        if len(self.project_token) < 32:
            raise LauncherClientError("sandbox launcher project token is unavailable")
        return selected, self.project_token

    def ping(self) -> dict[str, Any]:
        return self._request({"action": "ping"}, timeout=10)

    def probe(self, project: str | None = None) -> dict[str, Any]:
        selected, token = self._project_credentials(project)
        response = self._request(
            {
                "action": "probe",
                "project": selected,
                "project_token": token,
            },
            timeout=60,
        )
        result = response.get("result")
        if not isinstance(result, dict):
            raise LauncherClientError("sandbox launcher probe result is invalid")
        return result

    def cancel(self, run_id: str) -> bool:
        project, token = self._project_credentials()
        response = self._request(
            {
                "action": "cancel",
                "run_id": run_id,
                "project": project,
                "project_token": token,
            },
            timeout=20,
        )
        return bool(response.get("cancelled"))

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
        selected, token = self._project_credentials(project)
        response = self._request(
            {
                "action": "run",
                "run_id": run_id,
                "project": selected,
                "project_token": token,
                "workspace": str(workspace),
                "model": model,
                "route": route,
                "mutation_policy": mutation_policy,
                "timeout_seconds": timeout_seconds,
                "prompt": prompt,
            },
            timeout=float(timeout_seconds + 90),
        )
        result = response.get("result")
        if not isinstance(result, dict):
            raise LauncherClientError("sandbox launcher run result is invalid")
        expected = {
            "returncode",
            "stdout",
            "stderr",
            "cancelled",
            "execution_started",
        }
        if set(result) != expected:
            raise LauncherClientError("sandbox launcher result fields are invalid")
        return result
