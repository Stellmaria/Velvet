from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

_RUN_ID = re.compile(r"^[a-f0-9]{32}$")
_NETWORK_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_PROJECTS = frozenset({"velvet", "max"})
_MODELS = frozenset(
    {"gpt-5.4-mini", "gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"}
)
_ROUTES = frozenset({"codex_subscription", "byesu_provider"})
_MUTATION_POLICIES = frozenset({"read_only", "workspace_write"})
_ROUTE_MODELS = {
    "codex_subscription": frozenset(
        {"gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"}
    ),
    "byesu_provider": frozenset(
        {"gpt-5.4-mini", "gpt-5.6-luna", "gpt-5.6-terra"}
    ),
}
_EXECUTION_ITEM_TYPES = frozenset(
    {
        "command_execution",
        "file_change",
        "mcp_tool_call",
        "collab_tool_call",
        "dynamic_tool_call",
    }
)
_COMMON_HOME_FILES = (
    "AGENTS.md",
    "output.schema.json",
    "context-manifest.json",
)
_SUBSCRIPTION_HOME_FILES = ("auth.json", "config.toml")
_MAX_REQUEST_BYTES = 131_072
_MAX_OUTPUT_BYTES = 900_000

ROOT = Path(os.environ.get("HERMES_CODERS_ROOT", "/srv/hermes-coders")).resolve()
SOURCE_DIR = Path(
    os.environ.get(
        "HERMES_SANDBOX_INSTALL_DIR",
        "/usr/local/lib/hermes-sandbox-launcher/current",
    )
).resolve()
PROJECTION_ROOT = Path(
    os.environ.get(
        "HERMES_SANDBOX_PROJECTION_ROOT",
        "/run/hermes-sandbox-private",
    )
).resolve()
NETWORK = os.environ.get(
    "HERMES_SANDBOX_NETWORK", "hermes-sandbox-egress"
).strip()
if not _NETWORK_NAME.fullmatch(NETWORK):
    raise RuntimeError("HERMES_SANDBOX_NETWORK имеет небезопасное имя")
UID = int(os.environ.get("HERMES_UID", "10000"))
GID = int(os.environ.get("HERMES_GID", "10000"))
IMAGES = {
    "velvet": os.environ.get("HERMES_SANDBOX_VELVET_IMAGE", "").strip(),
    "max": os.environ.get("HERMES_SANDBOX_MAX_IMAGE", "").strip(),
}


class LauncherProtocolError(RuntimeError):
    pass


def audit(event: str, **fields: Any) -> None:
    payload = {"event": event, "timestamp": time.time(), **fields}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def exact_fields(payload: dict[str, Any], expected: set[str]) -> None:
    if set(payload) != expected:
        raise LauncherProtocolError("request fields do not match the fixed schema")


def validate_image_ids() -> None:
    invalid = [project for project, image in IMAGES.items() if not _IMAGE_ID.fullmatch(image)]
    if invalid:
        raise RuntimeError(
            "Immutable sandbox image IDs are missing for: " + ", ".join(invalid)
        )


def validate_run(payload: dict[str, Any]) -> dict[str, Any]:
    exact_fields(
        payload,
        {
            "action",
            "run_id",
            "project",
            "project_token",
            "workspace",
            "model",
            "route",
            "mutation_policy",
            "timeout_seconds",
            "prompt",
        },
    )
    if payload.get("action") != "run":
        raise LauncherProtocolError("invalid run action")
    run_id = payload.get("run_id")
    project = payload.get("project")
    workspace = payload.get("workspace")
    model = payload.get("model")
    route = payload.get("route")
    mutation_policy = payload.get("mutation_policy")
    timeout_seconds = payload.get("timeout_seconds")
    prompt = payload.get("prompt")
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise LauncherProtocolError("invalid run_id")
    if project not in _PROJECTS:
        raise LauncherProtocolError("invalid project")
    expected_workspace = f"/opt/codex-runs/workspaces/{run_id}"
    if workspace != expected_workspace:
        raise LauncherProtocolError("workspace is not the effective per-run path")
    if model not in _MODELS:
        raise LauncherProtocolError("model is not allowlisted")
    if route not in _ROUTES:
        raise LauncherProtocolError("route is not allowlisted")
    if model not in _ROUTE_MODELS[str(route)]:
        raise LauncherProtocolError("model is not allowed for the selected route")
    if mutation_policy not in _MUTATION_POLICIES:
        raise LauncherProtocolError("mutation policy is not allowlisted")
    if not isinstance(timeout_seconds, int) or not 60 <= timeout_seconds <= 14_400:
        raise LauncherProtocolError("timeout is outside the bounded range")
    if not isinstance(prompt, str) or not prompt or len(prompt) > 40_000:
        raise LauncherProtocolError("prompt is empty or too large")
    return {
        "run_id": run_id,
        "project": project,
        "workspace": workspace,
        "model": model,
        "route": route,
        "mutation_policy": mutation_policy,
        "timeout_seconds": timeout_seconds,
        "prompt": prompt,
    }


def host_workspace(project: str, run_id: str) -> Path:
    root = (ROOT / "codex-runs" / project / "workspaces").resolve()
    raw_target = root / run_id
    if raw_target.is_symlink():
        raise LauncherProtocolError("host workspace must not be a symlink")
    target = raw_target.resolve()
    if target.parent != root:
        raise LauncherProtocolError("unsafe host workspace path")
    git_marker = target / ".git"
    if not target.is_dir() or git_marker.is_symlink() or not git_marker.exists():
        raise LauncherProtocolError("host workspace is not a prepared Git checkout")
    return target


def container_name(project: str, run_id: str) -> str:
    return f"hermes-codex-{project}-{run_id}"


def project_codex_home(project: str) -> Path:
    parent = (ROOT / "codex").resolve()
    raw = parent / project
    if raw.is_symlink():
        raise LauncherProtocolError("project Codex home must not be a symlink")
    resolved = raw.resolve()
    if resolved.parent != parent or not resolved.is_dir():
        raise LauncherProtocolError("project Codex home is missing")
    return resolved


def create_codex_projection(project: str, run_id: str, route: str) -> Path:
    source = project_codex_home(project)
    PROJECTION_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chown(PROJECTION_ROOT, 0, 0)
    os.chmod(PROJECTION_ROOT, 0o700)
    target = Path(
        tempfile.mkdtemp(prefix=f"{project}-{run_id}-", dir=PROJECTION_ROOT)
    ).resolve()
    if target.parent != PROJECTION_ROOT:
        raise LauncherProtocolError("unsafe Codex projection path")
    names = list(_COMMON_HOME_FILES)
    if route == "codex_subscription":
        names.extend(_SUBSCRIPTION_HOME_FILES)
    try:
        for name in names:
            source_file = source / name
            if source_file.is_symlink() or not source_file.is_file():
                raise LauncherProtocolError(
                    f"required Codex projection file is invalid: {name}"
                )
            destination = target / name
            shutil.copyfile(source_file, destination)
            os.chown(destination, UID, GID)
            os.chmod(destination, 0o400)
        os.chown(target, UID, GID)
        os.chmod(target, 0o500)
        return target
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise


def build_docker_command(
    request: dict[str, Any],
    env_file: Path,
    codex_projection: Path,
) -> list[str]:
    project = str(request["project"])
    run_id = str(request["run_id"])
    mutation_policy = str(request["mutation_policy"])
    workspace = host_workspace(project, run_id)
    projection = codex_projection.resolve()
    if projection.parent != PROJECTION_ROOT or projection.is_symlink() or not projection.is_dir():
        raise LauncherProtocolError("unsafe Codex projection mount")
    entrypoint = (SOURCE_DIR / "sandbox_entrypoint.py").resolve()
    if entrypoint.parent != SOURCE_DIR or not entrypoint.is_file():
        raise LauncherProtocolError("sandbox entrypoint is missing")
    workspace_mount = f"type=bind,src={workspace},dst=/workspace"
    if mutation_policy == "read_only":
        workspace_mount += ",readonly"
    return [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--init",
        "--pull=never",
        "--log-driver=none",
        "--ipc=none",
        "--name",
        container_name(project, run_id),
        "--label",
        "hermes.sandbox=1",
        "--label",
        f"hermes.run_id={run_id}",
        "--label",
        f"hermes.project={project}",
        "--label",
        f"hermes.route={request['route']}",
        "--label",
        f"hermes.mutation_policy={mutation_policy}",
        "--read-only",
        "--user",
        f"{UID}:{GID}",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--security-opt=apparmor=hermes-codex-run",
        "--pids-limit=256",
        "--memory=6g",
        "--memory-swap=6g",
        "--cpus=3.0",
        "--network",
        NETWORK,
        "--tmpfs",
        f"/tmp:rw,noexec,nosuid,nodev,size=1g,mode=1777,uid={UID},gid={GID}",
        "--tmpfs",
        f"/opt/codex:rw,nosuid,nodev,size=512m,mode=0700,uid={UID},gid={GID}",
        "--mount",
        workspace_mount,
        "--mount",
        f"type=bind,src={projection},dst=/opt/codex-ro,readonly",
        "--mount",
        f"type=bind,src={entrypoint},dst=/app/hermes_sandbox_entrypoint.py,readonly",
        "--env-file",
        str(env_file),
        "--env",
        f"HERMES_SANDBOX_PROJECT={project}",
        "--env",
        f"HERMES_SANDBOX_MODEL={request['model']}",
        "--env",
        f"HERMES_SANDBOX_ROUTE={request['route']}",
        "--env",
        f"HERMES_SANDBOX_MUTATION_POLICY={mutation_policy}",
        "--env",
        "HOME=/opt/codex",
        "--env",
        "CODEX_HOME=/opt/codex",
        "--workdir",
        "/workspace",
        "--entrypoint",
        "python",
        IMAGES[project],
        "/app/hermes_sandbox_entrypoint.py",
    ]


def write_env_file(request: dict[str, Any]) -> Path:
    project = str(request["project"])
    run_id = str(request["run_id"])
    route = str(request["route"])
    model = str(request["model"])
    source = ROOT / "secrets" / f"{project}.env"
    if not source.is_file():
        raise LauncherProtocolError("project secret environment is missing")
    values = parse_env(source)
    selected = {"GH_TOKEN": values.get("GH_TOKEN", "")}
    if route == "byesu_provider":
        provider_key = (
            "BYESU_HERMES_GPT_PRO_API_KEY"
            if model == "gpt-5.6-luna"
            else "BYESU_HERMES_CODEX_API_KEY"
        )
        selected[provider_key] = values.get(provider_key, "")
        if not selected[provider_key]:
            raise LauncherProtocolError("selected provider credential is missing")
    if not selected["GH_TOKEN"]:
        raise LauncherProtocolError("project GH_TOKEN is missing")
    for value in selected.values():
        if "\n" in value or "\r" in value or "\0" in value:
            raise LauncherProtocolError("secret environment contains unsafe characters")
    runtime_dir = Path("/run/hermes-sandbox")
    runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
    fd, name = tempfile.mkstemp(
        prefix=f".{project}-{run_id}.", suffix=".env", dir=runtime_dir
    )
    path = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for key, value in selected.items():
                if value:
                    handle.write(f"{key}={value}\n")
            handle.flush()
            os.fsync(handle.fileno())
        path.chmod(0o600)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def execution_started(stdout: str) -> bool:
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip().casefold()
        if item_type in _EXECUTION_ITEM_TYPES:
            return True
        if item_type.endswith("_tool_call") or item_type.endswith("_execution"):
            return True
    return False
