#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

from codex_first_runner import Handler, ThreadingHTTPServer
from codex_provider_chain_runner import ProviderChainManager
from codex_runner import utc_now


class AuditedTierProviderManager(ProviderChainManager):
    """Record successful mutations and fail closed for read-only runs."""

    def __init__(self) -> None:
        super().__init__()
        self._baseline_lock = threading.RLock()
        self._isolation_lock = threading.Lock()
        self._run_baselines: dict[str, str] = {}
        self._base_workspace = self.workspace
        self._worktree_root = Path(
            os.environ.get(
                "CODEX_ISOLATED_WORKTREE_ROOT", str(self.store.root / "workspaces")
            )
        ).resolve()
        self._worktree_root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _worktree_git(self, *args: str, cwd: Path | None = None) -> None:
        result = subprocess.run(
            ["git", *args], cwd=cwd or self._base_workspace, check=False,
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "isolated worktree setup failed: "
                + (result.stderr.strip() or f"git exit {result.returncode}")[-1000:]
            )

    def _prepare_worktree(self, run_id: str) -> Path:
        target = (self._worktree_root / run_id).resolve()
        if target.parent != self._worktree_root:
            raise RuntimeError("unsafe isolated worktree path")
        result = subprocess.run(
            ["git", "remote", "show", "origin"], cwd=self._base_workspace,
            check=False, capture_output=True, text=True, timeout=120,
        )
        match = re.search(r"^\s*HEAD branch:\s*([^\s]+)\s*$", result.stdout, re.MULTILINE)
        default_branch = match.group(1) if result.returncode == 0 and match else ""
        valid_ref = subprocess.run(
            ["git", "check-ref-format", "--branch", default_branch],
            cwd=self._base_workspace, check=False, capture_output=True, text=True,
            timeout=10,
        )
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,254}", default_branch)
            or valid_ref.returncode != 0
        ):
            raise RuntimeError("origin did not report a safe default branch")
        self._worktree_git("fetch", "--prune", "origin", default_branch)
        base_ref = f"origin/{default_branch}"
        try:
            self._worktree_git(
                "worktree", "add", "--detach", str(target), base_ref
            )
        except RuntimeError:
            if target.parent == self._worktree_root and target.exists():
                shutil.rmtree(target)
            raise
        return target

    def _cleanup_worktree(self, target: Path) -> None:
        try:
            self._worktree_git("worktree", "remove", "--force", str(target))
        except RuntimeError as error:
            self.store.update(
                target.name,
                cleanup_error=str(error),
                last_event={"type": "isolated_workspace_cleanup_failed"},
            )
        finally:
            if target.parent == self._worktree_root and target.exists():
                shutil.rmtree(target)

    def capabilities(self) -> dict[str, Any]:
        payload = super().capabilities()
        routing = payload.get("routing")
        if not isinstance(routing, dict):
            routing = {}
        return {
            **payload,
            "routing": {
                **routing,
                "mutation_audit": {
                    "successful_runs": True,
                    "read_only_fail_closed": True,
                },
            },
        }

    def _execute(
        self,
        run_id: str,
        prompt: str,
        instructions: str,
        selected_model: str,
    ) -> None:
        with self._isolation_lock:
            isolated = self._prepare_worktree(run_id)
            self.workspace = isolated
            self.store.update(run_id, workspace=str(isolated))
            try:
                with self._baseline_lock:
                    self._run_baselines[run_id] = self._fingerprint()
                super()._execute(run_id, prompt, instructions, selected_model)
            finally:
                self.workspace = self._base_workspace
                with self._baseline_lock:
                    self._run_baselines.pop(run_id, None)
                self._cleanup_worktree(isolated)

    def _success(
        self,
        run_id: str,
        model: str,
        models: list[str],
        routes: list[str],
        route: str,
        reason: str | None,
        stdout: str,
    ) -> None:
        with self._baseline_lock:
            baseline = self._run_baselines.get(run_id)
        mutated = baseline is not None and self._fingerprint() != baseline
        record = self.store.read(run_id)
        mutation_policy = str(record.get("mutation_policy") or "workspace_write")
        self.store.update(run_id, mutation_started=mutated)
        if mutation_policy == "read_only" and mutated:
            self.store.update(
                run_id,
                status="failed",
                finished_at=utc_now(),
                model=model,
                attempted_models=models,
                attempted_routes=routes,
                actual_route=route,
                fallback_reason=reason,
                mutation_started=True,
                error="Read-only run mutated the isolated workspace; result rejected.",
                last_event={
                    "type": "read_only_mutation_blocked",
                    "model": model,
                    "route": route,
                    "mutation_started": True,
                },
            )
            return
        super()._success(run_id, model, models, routes, route, reason, stdout)


def main() -> int:
    host = os.environ.get("CODEX_RUNNER_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.environ.get("CODEX_RUNNER_PORT", "8642"))
    if not 1024 <= port <= 65535:
        raise RuntimeError("CODEX_RUNNER_PORT должен быть от 1024 до 65535")
    manager = AuditedTierProviderManager()
    server = ThreadingHTTPServer((host, port), Handler)
    server.manager = manager  # type: ignore[attr-defined]
    print(
        f"Velvet audited tier-aware provider runner listening on {host}:{port}; "
        f"default={manager.default_model}; provider_catalog={manager.provider_models}",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
