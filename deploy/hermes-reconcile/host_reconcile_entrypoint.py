from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Sequence

_HOST_SCRIPT = Path("/usr/local/libexec/velvet-hermes-operator-reconcile.py")


def _load_host_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "velvet_hermes_operator_reconcile_installed",
        _HOST_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load installed Hermes reconcile host bridge")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _patch_runtime(host: ModuleType) -> None:
    base_runtime = host.ReconcileRuntime

    class VerifiedCheckoutRuntime(base_runtime):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            state_dir = getattr(self, "state_dir", None)
            if state_dir is not None:
                self.reconcile_tmp_dir = Path(state_dir) / "tmp"
                self.reconcile_tmp_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                os.chmod(self.reconcile_tmp_dir, 0o700)

        def _run(
            self,
            command: Sequence[str],
            *,
            timeout: int,
            check: bool = True,
        ) -> subprocess.CompletedProcess[str]:
            env = {
                "HOME": "/root",
                "LANG": os.getenv("LANG", "C.UTF-8"),
                "LC_ALL": os.getenv("LC_ALL", "C.UTF-8"),
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "DOCKER_CONFIG": "/srv/hermes-operator-control/reconcile-docker-config",
                "COMPOSE_BAKE": "false",
            }
            reconcile_tmp_dir = getattr(self, "reconcile_tmp_dir", None)
            if reconcile_tmp_dir is not None:
                # Docker bind sources are resolved by the host daemon, not by
                # systemd's PrivateTmp namespace. Keep installer temp files in
                # the existing host-visible reconcile state boundary.
                env["TMPDIR"] = str(reconcile_tmp_dir)
            completed = subprocess.run(
                list(command),
                cwd=self.app_dir,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
            if check and completed.returncode != 0:
                output = host._redact(
                    (completed.stdout or "")[-host._MAX_OUTPUT_BYTES :].strip()
                )
                raise RuntimeError(
                    f"Fixed reconcile command failed ({completed.returncode}).\n{output}"
                )
            return completed

        def _git_process(
            self,
            *arguments: str,
            check: bool = True,
        ) -> subprocess.CompletedProcess[str]:
            return self._run(
                [
                    "/usr/bin/git",
                    "--no-optional-locks",
                    "-c",
                    f"safe.directory={self.app_dir}",
                    "-C",
                    str(self.app_dir),
                    *arguments,
                ],
                timeout=90,
                check=check,
            )

        def _git(self, *arguments: str) -> str:
            result = self._git_process(*arguments)
            return (result.stdout or "").strip()

        def _verify_checkout(self) -> str:
            if not self.app_dir.is_dir():
                raise RuntimeError("Velvet production checkout is missing")
            top = Path(self._git("rev-parse", "--show-toplevel")).resolve()
            if top != self.app_dir:
                raise RuntimeError("Velvet production checkout root is unexpected")

            branch_result = self._git_process(
                "symbolic-ref",
                "--short",
                "HEAD",
                check=False,
            )
            if branch_result.returncode == 0:
                branch = (branch_result.stdout or "").strip()
                if branch != self.branch:
                    raise RuntimeError(
                        f"Velvet production checkout must be on {self.branch} or detached at fetched origin/{self.branch}; got {branch}"
                    )

            status = self._git("status", "--porcelain", "--untracked-files=all")
            if status:
                raise RuntimeError("Velvet production checkout is not clean")
            head = self._git("rev-parse", "HEAD")
            remote = self._git("rev-parse", f"refs/remotes/origin/{self.branch}")
            if head != remote:
                raise RuntimeError(
                    "Velvet production checkout does not match the fetched origin/main"
                )
            return head

    host.ReconcileRuntime = VerifiedCheckoutRuntime


def main() -> None:
    host = _load_host_module()
    _patch_runtime(host)
    host.main()


if __name__ == "__main__":
    main()
