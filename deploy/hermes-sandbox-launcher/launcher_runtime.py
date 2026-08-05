from __future__ import annotations

import os
import signal
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from launcher_contract import (
    GID,
    IMAGES,
    NETWORK,
    ROOT,
    UID,
    LauncherProtocolError,
    _LAUNCHER_LABEL,
    _MAX_OUTPUT_BYTES,
    _PROJECTS,
    _RUN_ID,
    audit,
    build_docker_command,
    cleanup_codex_projection,
    container_name,
    create_codex_projection,
    execution_started,
    write_env_file,
)


class Launcher:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._containers: dict[str, str] = {}
        self._cancelled: set[str] = set()
        self._active: dict[str, str] = {}
        self._verify_runtime_prerequisites()

    @staticmethod
    def _checked(
        args: list[str], *, timeout: int, error: str
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                args,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(error) from exc
        if result.returncode != 0:
            raise RuntimeError(error)
        return result

    def _verify_runtime_prerequisites(self) -> None:
        self._checked(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            timeout=20,
            error="Docker daemon is unavailable to sandbox launcher",
        )
        self._checked(
            ["docker", "network", "inspect", NETWORK],
            timeout=20,
            error=f"Sandbox network is unavailable: {NETWORK}",
        )

    def _verify_image(self, project: str) -> None:
        image = IMAGES[project]
        self._checked(
            ["docker", "image", "inspect", image],
            timeout=20,
            error=f"Pinned sandbox image is unavailable for {project}",
        )

    def cleanup_stale(self) -> None:
        result = self._checked(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                "label=hermes.sandbox=1",
                "--filter",
                f"label=hermes.launcher={_LAUNCHER_LABEL}",
            ],
            timeout=30,
            error="Unable to enumerate stale sandbox containers",
        )
        identifiers = [item.strip() for item in result.stdout.splitlines() if item.strip()]
        if not identifiers:
            return
        self._checked(
            ["docker", "rm", "-f", *identifiers],
            timeout=60,
            error="Unable to remove stale sandbox containers",
        )
        audit("stale_containers_removed", count=len(identifiers))

    def _stop_container(
        self,
        project: str,
        run_id: str,
        *,
        mark_cancelled: bool,
    ) -> bool:
        if project not in _PROJECTS or not _RUN_ID.fullmatch(run_id):
            raise LauncherProtocolError("invalid cancellation target")
        with self._lock:
            if self._active.get(run_id) != project:
                return False
            if mark_cancelled:
                self._cancelled.add(run_id)
            process = self._processes.get(run_id)
            name = self._containers.get(run_id)
        if process is None or name is None:
            return True
        try:
            subprocess.run(
                ["docker", "stop", "--time", "10", name],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            if process.poll() is None:
                subprocess.run(
                    ["docker", "kill", name],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
        except (OSError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        return True

    def cancel(self, project: str, run_id: str) -> bool:
        stopped = self._stop_container(project, run_id, mark_cancelled=True)
        if stopped:
            audit("run_cancel_requested", run_id=run_id, project=project)
        return stopped

    def run(self, request: dict[str, Any]) -> dict[str, Any]:
        run_id = str(request["run_id"])
        project = str(request["project"])
        with self._lock:
            if run_id in self._active:
                raise LauncherProtocolError("run_id is already active")
            self._active[run_id] = project
        env_file: Path | None = None
        projection: Path | None = None
        process: subprocess.Popen[str] | None = None
        name = container_name(project, run_id)
        started = time.monotonic()
        try:
            self._verify_image(project)
            env_file = write_env_file(request)
            projection = create_codex_projection(
                project,
                run_id,
                str(request["route"]),
            )
            command = build_docker_command(request, env_file, projection)
            audit(
                "run_started",
                run_id=run_id,
                project=project,
                model=request["model"],
                route=request["route"],
                mutation_policy=request["mutation_policy"],
                image=IMAGES[project],
                network=NETWORK,
            )
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            with self._lock:
                self._processes[run_id] = process
                self._containers[run_id] = name
                cancelled_before_start = run_id in self._cancelled
            if cancelled_before_start:
                self._stop_container(project, run_id, mark_cancelled=True)

            timed_out = False
            try:
                stdout, stderr = process.communicate(
                    input=str(request["prompt"]),
                    timeout=int(request["timeout_seconds"]),
                )
            except subprocess.TimeoutExpired:
                timed_out = True
                self._stop_container(project, run_id, mark_cancelled=False)
                try:
                    stdout, stderr = process.communicate(timeout=20)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    stdout, stderr = process.communicate()
                stderr = (stderr or "") + "\nSandbox run timed out"

            with self._lock:
                cancelled = run_id in self._cancelled
            raw_stdout = stdout or ""
            returncode = process.returncode if process.returncode is not None else 1
            if timed_out and returncode == 0:
                returncode = 124
            result = {
                "returncode": returncode,
                "stdout": raw_stdout[-_MAX_OUTPUT_BYTES:],
                "stderr": (stderr or "")[-_MAX_OUTPUT_BYTES:],
                "cancelled": cancelled,
                "execution_started": execution_started(raw_stdout),
            }
            audit(
                "run_finished",
                run_id=run_id,
                project=project,
                returncode=result["returncode"],
                cancelled=cancelled,
                timed_out=timed_out,
                execution_started=result["execution_started"],
                duration_seconds=round(time.monotonic() - started, 3),
            )
            return result
        finally:
            cleanup_errors: list[str] = []
            if env_file is not None:
                try:
                    env_file.unlink(missing_ok=True)
                except OSError as error:
                    cleanup_errors.append(type(error).__name__)
            try:
                subprocess.run(
                    ["docker", "rm", "-f", name],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                cleanup_errors.append(type(error).__name__)
            if projection is not None:
                try:
                    cleanup_codex_projection(projection)
                except (OSError, LauncherProtocolError) as error:
                    cleanup_errors.append(type(error).__name__)
            with self._lock:
                self._processes.pop(run_id, None)
                self._containers.pop(run_id, None)
                self._cancelled.discard(run_id)
                self._active.pop(run_id, None)
            if cleanup_errors:
                audit(
                    "run_cleanup_failed",
                    run_id=run_id,
                    project=project,
                    error_types=cleanup_errors,
                )

    def probe(self, project: str) -> dict[str, Any]:
        if project not in _PROJECTS:
            raise LauncherProtocolError("invalid project")
        self._verify_image(project)
        probe_root = (ROOT / "codex-runs" / project / "probes").resolve()
        probe_root.mkdir(parents=True, exist_ok=True, mode=0o750)
        target = Path(tempfile.mkdtemp(prefix="launcher-", dir=probe_root)).resolve()
        if target.parent != probe_root:
            raise LauncherProtocolError("unsafe probe workspace")
        os.chown(target, UID, GID)
        name = f"hermes-probe-{project}-{target.name[-8:]}"
        script = """from pathlib import Path
p = Path('/workspace/probe.txt')
p.write_text('ok')
assert not Path('/run/docker.sock').exists()
assert not Path('/var/run/docker.sock').exists()
assert not Path('/run/hermes-sandbox').exists()
assert not Path('/workspace-base').exists()
assert not Path('/opt/codex-runs').exists()
status = Path('/proc/1/status').read_text()
assert 'NoNewPrivs:\\t1' in status
assert 'CapEff:\\t0000000000000000' in status
assert 'Seccomp:\\t2' in status
assert 'hermes-codex-run' in Path('/proc/1/attr/current').read_text()
blocked = False
try:
    Path('/etc/hermes-probe').write_text('x')
except OSError:
    blocked = True
assert blocked
"""
        command = [
            "docker",
            "run",
            "--rm",
            "--init",
            "--pull=never",
            "--log-driver=none",
            "--ipc=none",
            "--name",
            name,
            "--label",
            "hermes.sandbox=1",
            "--label",
            f"hermes.launcher={_LAUNCHER_LABEL}",
            "--label",
            f"hermes.project={project}",
            "--read-only",
            "--user",
            f"{UID}:{GID}",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--security-opt=apparmor=hermes-codex-run",
            "--pids-limit=64",
            "--memory=256m",
            "--memory-swap=256m",
            "--cpus=0.5",
            "--network",
            "none",
            "--tmpfs",
            f"/tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777,uid={UID},gid={GID}",
            "--mount",
            f"type=bind,src={target},dst=/workspace",
            "--entrypoint",
            "python",
            IMAGES[project],
            "-c",
            script,
        ]
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=45,
            )
            audit("probe_finished", project=project, returncode=result.returncode)
            return {
                "returncode": result.returncode,
                "stdout": (result.stdout or "")[-20_000:],
                "stderr": (result.stderr or "")[-20_000:],
            }
        finally:
            subprocess.run(
                ["docker", "rm", "-f", name],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            shutil.rmtree(target, ignore_errors=True)

    def shutdown(self) -> None:
        with self._lock:
            active = list(self._active.items())
        for run_id, project in active:
            try:
                self._stop_container(project, run_id, mark_cancelled=False)
            except Exception:
                pass
