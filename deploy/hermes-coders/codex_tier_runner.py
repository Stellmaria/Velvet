#!/usr/bin/env python3
from __future__ import annotations

import hashlib
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


_SAFE_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,254}")


class AuditedTierProviderManager(ProviderChainManager):
    """Run every task in a disposable clone and audit Git effects explicitly."""

    def __init__(self) -> None:
        super().__init__()
        self._baseline_lock = threading.RLock()
        self._isolation_lock = threading.Lock()
        self._run_baselines: dict[str, dict[str, str]] = {}
        self._base_baselines: dict[str, dict[str, str]] = {}
        self._base_workspace = Path(
            os.environ.get("CODEX_WORKSPACE_BASE", str(self.workspace))
        ).resolve()
        self._workspace_root = Path(
            os.environ.get(
                "CODEX_ISOLATED_WORKSPACE_ROOT", str(self.store.root / "workspaces")
            )
        ).resolve()
        if not self._base_workspace.is_dir():
            raise RuntimeError(f"read-only base workspace missing: {self._base_workspace}")
        if self._base_workspace == self._workspace_root or self._workspace_root in self._base_workspace.parents:
            raise RuntimeError("isolated workspace root overlaps the base checkout")
        self._workspace_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.workspace = self._base_workspace

    @staticmethod
    def _run_git(cwd: Path, *args: str, timeout: int = 120) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            details = (result.stderr.strip() or f"git exit {result.returncode}")[-1500:]
            raise RuntimeError(f"isolated workspace Git failed: {details}")
        return result.stdout

    @classmethod
    def _snapshot(cls, workspace: Path) -> dict[str, str]:
        head = cls._run_git(workspace, "rev-parse", "HEAD").strip()
        branch = cls._run_git(
            workspace, "rev-parse", "--abbrev-ref", "HEAD"
        ).strip()
        refs = cls._run_git(
            workspace,
            "for-each-ref",
            "--format=%(refname)%00%(objectname)%00",
            "refs/heads",
            "refs/tags",
        )
        status = cls._run_git(
            workspace,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        )
        return {
            "head": head,
            "branch": branch,
            "refs_sha256": hashlib.sha256(refs.encode("utf-8")).hexdigest(),
            "status_sha256": hashlib.sha256(status.encode("utf-8")).hexdigest(),
        }

    @staticmethod
    def _changed(before: dict[str, str], after: dict[str, str]) -> dict[str, bool]:
        return {
            "head_changed": before["head"] != after["head"],
            "branch_changed": before["branch"] != after["branch"],
            "refs_changed": before["refs_sha256"] != after["refs_sha256"],
            "working_tree_changed": before["status_sha256"] != after["status_sha256"],
        }

    def _default_branch(self) -> str:
        local = subprocess.run(
            ["git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
            cwd=self._base_workspace,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        branch = ""
        if local.returncode == 0:
            value = local.stdout.strip()
            if value.startswith("origin/"):
                branch = value.removeprefix("origin/")
        if not branch:
            remote = subprocess.run(
                ["git", "remote", "show", "origin"],
                cwd=self._base_workspace,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            match = re.search(
                r"^\s*HEAD branch:\s*([^\s]+)\s*$", remote.stdout, re.MULTILINE
            )
            branch = match.group(1) if remote.returncode == 0 and match else ""
        valid = subprocess.run(
            ["git", "check-ref-format", "--branch", branch],
            cwd=self._base_workspace,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if not _SAFE_BRANCH.fullmatch(branch) or valid.returncode != 0:
            raise RuntimeError("origin did not report a safe default branch")
        return branch

    def _prepare_workspace(self, run_id: str) -> tuple[Path, str]:
        target = (self._workspace_root / run_id).resolve()
        if target.parent != self._workspace_root or target.is_symlink():
            raise RuntimeError("unsafe isolated workspace path")
        if target.exists():
            shutil.rmtree(target)

        origin_url = self._run_git(self._base_workspace, "remote", "get-url", "origin").strip()
        default_branch = self._default_branch()
        clone = subprocess.run(
            [
                "git",
                "clone",
                "--no-hardlinks",
                "--no-checkout",
                str(self._base_workspace),
                str(target),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if clone.returncode != 0:
            if target.exists() and target.parent == self._workspace_root:
                shutil.rmtree(target)
            raise RuntimeError(
                "isolated clone failed: "
                + (clone.stderr.strip() or f"git exit {clone.returncode}")[-1500:]
            )
        try:
            self._run_git(target, "remote", "set-url", "origin", origin_url)
            self._run_git(target, "fetch", "--prune", "origin", default_branch, timeout=180)
            source_ref = f"origin/{default_branch}"
            self._run_git(target, "checkout", "--detach", "--force", source_ref)
        except Exception:
            if target.exists() and target.parent == self._workspace_root:
                shutil.rmtree(target)
            raise
        return target, source_ref

    def _cleanup_workspace(self, target: Path) -> None:
        if target.parent != self._workspace_root or target.is_symlink():
            self.store.update(
                target.name,
                cleanup_error="unsafe isolated workspace cleanup path",
                last_event={"type": "isolated_workspace_cleanup_failed"},
            )
            return
        try:
            if target.exists():
                shutil.rmtree(target)
        except OSError as error:
            self.store.update(
                target.name,
                cleanup_error=str(error),
                last_event={"type": "isolated_workspace_cleanup_failed"},
            )

    def capabilities(self) -> dict[str, Any]:
        payload = super().capabilities()
        routing = payload.get("routing")
        if not isinstance(routing, dict):
            routing = {}
        return {
            **payload,
            "routing": {
                **routing,
                "workspace_isolation": {
                    "per_run_clone": True,
                    "base_checkout_read_only": True,
                    "legacy_workspace_path": False,
                },
                "mutation_audit": {
                    "successful_runs": True,
                    "head_and_refs": True,
                    "working_tree": True,
                    "base_checkout": True,
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
            isolated, source_ref = self._prepare_workspace(run_id)
            self.workspace = isolated
            isolated_before = self._snapshot(isolated)
            base_before = self._snapshot(self._base_workspace)
            with self._baseline_lock:
                self._run_baselines[run_id] = isolated_before
                self._base_baselines[run_id] = base_before
            self.store.update(
                run_id,
                workspace=str(isolated),
                workspace_path=str(isolated),
                process_cwd=str(isolated),
                workspace_source_ref=source_ref,
                baseline_head=isolated_before["head"],
                base_workspace=str(self._base_workspace),
            )
            workspace_notice = (
                f"EFFECTIVE RUN WORKSPACE: {isolated}\n"
                "This current working directory is the only task checkout. "
                "Do not access /workspace, /workspace-base, chat workspaces or sibling runs."
            )
            combined_prompt = f"{workspace_notice}\n\n{prompt}"
            combined_instructions = (
                f"{workspace_notice}\n\n{instructions}" if instructions else workspace_notice
            )
            try:
                super()._execute(
                    run_id,
                    combined_prompt,
                    combined_instructions,
                    selected_model,
                )
                base_after = self._snapshot(self._base_workspace)
                base_delta = self._changed(base_before, base_after)
                if any(base_delta.values()):
                    self.store.update(
                        run_id,
                        status="failed",
                        finished_at=utc_now(),
                        mutation_started=True,
                        base_workspace_changed=True,
                        error="Shared read-only base checkout changed during the run.",
                        last_event={
                            "type": "base_workspace_mutation_blocked",
                            **base_delta,
                        },
                    )
            finally:
                self.workspace = self._base_workspace
                with self._baseline_lock:
                    self._run_baselines.pop(run_id, None)
                    self._base_baselines.pop(run_id, None)
                self._cleanup_workspace(isolated)

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
            isolated_before = self._run_baselines.get(run_id)
            base_before = self._base_baselines.get(run_id)
        isolated_after = self._snapshot(self.workspace)
        base_after = self._snapshot(self._base_workspace)
        isolated_delta = (
            self._changed(isolated_before, isolated_after) if isolated_before else {}
        )
        base_delta = self._changed(base_before, base_after) if base_before else {}
        git_mutated = any(isolated_delta.values()) or any(base_delta.values())
        record = self.store.read(run_id)
        execution_started = record.get("execution_started") is True
        mutation_policy = str(record.get("mutation_policy") or "workspace_write")

        evidence = {
            "baseline_head": isolated_before.get("head") if isolated_before else None,
            "final_head": isolated_after["head"],
            "final_branch": isolated_after["branch"],
            "head_changed": bool(isolated_delta.get("head_changed")),
            "branch_changed": bool(isolated_delta.get("branch_changed")),
            "refs_changed": bool(isolated_delta.get("refs_changed")),
            "working_tree_changed": bool(isolated_delta.get("working_tree_changed")),
            "base_workspace_changed": any(base_delta.values()),
            "execution_started": execution_started,
        }
        self.store.update(run_id, mutation_started=git_mutated, **evidence)
        if mutation_policy == "read_only" and git_mutated:
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
                error="Read-only run mutated Git state; result rejected.",
                last_event={
                    "type": "read_only_mutation_blocked",
                    "model": model,
                    "route": route,
                    **evidence,
                },
            )
            return

        super()._success(run_id, model, models, routes, route, reason, stdout)
        completed = self.store.read(run_id)
        execution_started = completed.get("execution_started") is True
        structured = completed.get("structured_output")
        push_or_pr_observed = bool(
            isinstance(structured, dict)
            and (str(structured.get("branch") or "") or str(structured.get("pr") or ""))
        )
        mutation_started = git_mutated or execution_started or push_or_pr_observed
        self.store.update(
            run_id,
            mutation_started=mutation_started,
            push_or_pr_observed=push_or_pr_observed,
            **evidence,
        )


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
