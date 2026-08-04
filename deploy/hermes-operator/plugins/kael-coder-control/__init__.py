"""Fail-closed coder delegation policy for the main Hermes agent, Kael."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


PROJECTS = ("velvet", "max")
TASK_TYPES = ("general", "code", "read_only", "documentation", "incident")
COMPLEXITIES = ("small", "standard", "complex")
RISKS = ("low", "medium", "high", "critical")
MUTATION_POLICIES = ("read_only", "workspace_write", "isolated_pr_only")
TIERS = ("small", "standard", "complex", "high_risk")

_REQUIRED_FIELDS = frozenset(
    {
        "project",
        "task_type",
        "complexity",
        "risk",
        "mutation_policy",
        "requested_tier",
        "task",
    }
)

CODER_DELEGATE_SCHEMA = {
    "description": (
        "Delegate a Velvet or Max repository task through the canonical coder "
        "router. This is the only permitted way to start coder work."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_REQUIRED_FIELDS),
        "properties": {
            "project": {
                "type": "string",
                "enum": list(PROJECTS),
                "description": "Target project.",
            },
            "task_type": {
                "type": "string",
                "enum": list(TASK_TYPES),
            },
            "complexity": {
                "type": "string",
                "enum": list(COMPLEXITIES),
            },
            "risk": {
                "type": "string",
                "enum": list(RISKS),
            },
            "mutation_policy": {
                "type": "string",
                "enum": list(MUTATION_POLICIES),
            },
            "requested_tier": {
                "type": "string",
                "enum": list(TIERS),
            },
            "task": {
                "type": "string",
                "minLength": 1,
                "maxLength": 24000,
                "description": "Complete task for the selected coder.",
            },
        },
    },
}

_CONTROLLER_POLICIES: dict[str, frozenset[str] | None] = {
    "/opt/data/tools/monitorctl.py": None,
    "/opt/data/tools/opsctl.py": None,
    "/opt/data/tools/reconcilectl.py": None,
    "/opt/data/tools/runctl.py": None,
    "/opt/data/tools/coderctl.py": frozenset(
        {"health", "status", "wait", "list", "stop", "pr"}
    ),
}

_INTERPRETERS = frozenset(
    {
        "python",
        "python3",
        "/usr/bin/python3",
        sys.executable,
    }
)

_FILE_TOOLS = frozenset(
    {
        "read_file",
        "write_file",
        "patch",
        "edit_file",
        "replace_file",
        "list_directory",
        "find_files",
    }
)

_CODE_EXECUTION_TOOLS = frozenset(
    {
        "execute_code",
        "python",
        "python_repl",
        "shell_exec",
    }
)

_REPOSITORY_MARKERS = (
    "/opt/data/workspace/",
    "workspace/velvet",
    "workspace/max",
    "/srv/velvet",
    "/srv/romatic-club-max",
    "/srv/romatic_club_bot_max",
)

_GITHUB_TOOL_PATTERN = re.compile(
    r"(^|_)(git|github|gh)(_|$)",
    flags=re.IGNORECASE,
)

_SHELL_META_PATTERN = re.compile(r"[\n\r;&|><`$()]")

_BLOCK_MESSAGE = (
    "BLOCKED by Kael coder policy: repository and code work must use "
    "coder_delegate. Local terminal, search, code execution, Git, GitHub, "
    "and local coder workspace fallback are not permitted."
)


class CoderControlError(RuntimeError):
    """A fail-closed validation or delegation error."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit_path() -> Path:
    return Path(
        os.getenv(
            "KAEL_CODER_AUDIT_PATH",
            "/opt/data/audit/kael-coder-control.jsonl",
        )
    )


def _audit(event: str, **fields: Any) -> None:
    """Append one bounded JSON audit event without recording task text."""

    path = _audit_path()
    safe_fields: dict[str, Any] = {}
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            safe_fields[key] = value
        elif isinstance(value, (list, tuple)):
            safe_fields[key] = [
                item
                for item in value
                if isinstance(item, (str, int, float, bool))
            ][:32]

    entry = {
        "timestamp": _utc_now(),
        "event": event,
        **safe_fields,
    }
    encoded = (
        json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")

    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
        descriptor = os.open(
            path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o600,
        )
        try:
            os.write(descriptor, encoded)
        finally:
            os.close(descriptor)
    except OSError:
        # Audit failure must never turn a denied operation into an allowed one.
        return


def _json_result(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True)


def _error_result(
    message: str,
    *,
    requested_tier: str | None = None,
    project: str | None = None,
) -> str:
    return _json_result(
        {
            "ok": False,
            "error": message,
            "project": project,
            "requested_tier": requested_tier,
            "selected_primary_model": None,
            "actual_route": None,
            "attempted_routes": [],
            "mutation_started": False,
            "production_privileges": False,
        }
    )


def _validate_choice(
    args: Mapping[str, Any],
    field: str,
    choices: tuple[str, ...],
) -> str:
    value = args.get(field)
    if not isinstance(value, str) or value not in choices:
        raise CoderControlError(
            f"Invalid {field}; expected one of: {', '.join(choices)}"
        )
    return value


def _validate_delegate_args(raw_args: Any) -> dict[str, str]:
    if not isinstance(raw_args, Mapping):
        raise CoderControlError("Tool arguments must be a JSON object.")

    unknown = set(raw_args) - _REQUIRED_FIELDS
    missing = _REQUIRED_FIELDS - set(raw_args)
    if unknown:
        raise CoderControlError(
            "Unknown fields: " + ", ".join(sorted(str(item) for item in unknown))
        )
    if missing:
        raise CoderControlError(
            "Missing fields: " + ", ".join(sorted(missing))
        )

    task = raw_args.get("task")
    if not isinstance(task, str):
        raise CoderControlError("task must be a string.")
    task = task.strip()
    if not task:
        raise CoderControlError("task must not be empty.")
    if len(task) > 24000:
        raise CoderControlError("task exceeds 24000 characters.")

    return {
        "project": _validate_choice(raw_args, "project", PROJECTS),
        "task_type": _validate_choice(raw_args, "task_type", TASK_TYPES),
        "complexity": _validate_choice(raw_args, "complexity", COMPLEXITIES),
        "risk": _validate_choice(raw_args, "risk", RISKS),
        "mutation_policy": _validate_choice(
            raw_args,
            "mutation_policy",
            MUTATION_POLICIES,
        ),
        "requested_tier": _validate_choice(
            raw_args,
            "requested_tier",
            TIERS,
        ),
        "task": task,
    }


def _coderctl_path() -> str:
    return os.getenv(
        "KAEL_CODERCTL_PATH",
        "/opt/data/tools/coderctl.py",
    )


def _extract_coderctl_error(stderr: str) -> str:
    try:
        payload = json.loads(stderr.strip())
    except (json.JSONDecodeError, TypeError):
        return "Central coder delegation failed."

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, str) and error.strip():
            return error.strip()[:2000]
    return "Central coder delegation failed."


def _handle_coder_delegate(raw_args: Any, **_: Any) -> str:
    try:
        args = _validate_delegate_args(raw_args)
    except CoderControlError as error:
        _audit("delegate_rejected", reason=str(error)[:500])
        return _error_result(str(error))

    task_hash = hashlib.sha256(args["task"].encode("utf-8")).hexdigest()
    _audit(
        "coder_classification",
        project=args["project"],
        task_type=args["task_type"],
        complexity=args["complexity"],
        risk=args["risk"],
        mutation_policy=args["mutation_policy"],
        requested_tier=args["requested_tier"],
        task_sha256=task_hash,
        task_length=len(args["task"]),
    )
    _audit(
        "delegate_invocation",
        project=args["project"],
        requested_tier=args["requested_tier"],
        task_sha256=task_hash,
    )

    command = [
        sys.executable,
        _coderctl_path(),
        "--timeout",
        "30",
        "submit",
        args["project"],
        "--source",
        "kael-delegated",
        "--task-type",
        args["task_type"],
        "--complexity",
        args["complexity"],
        "--risk",
        args["risk"],
        "--mutation-policy",
        args["mutation_policy"],
        "--tier",
        args["requested_tier"],
        "--task",
        args["task"],
    ]

    _audit(
        "router_submit",
        project=args["project"],
        requested_tier=args["requested_tier"],
        task_sha256=task_hash,
    )

    try:
        completed = subprocess.run(
            command,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except (OSError, subprocess.SubprocessError) as error:
        _audit(
            "router_result",
            project=args["project"],
            requested_tier=args["requested_tier"],
            status="failed",
            error_type=type(error).__name__,
        )
        return _error_result(
            "Central coder delegation is unavailable.",
            requested_tier=args["requested_tier"],
            project=args["project"],
        )

    if completed.returncode != 0:
        message = _extract_coderctl_error(completed.stderr)
        _audit(
            "router_result",
            project=args["project"],
            requested_tier=args["requested_tier"],
            status="failed",
            exit_code=completed.returncode,
        )
        return _error_result(
            message,
            requested_tier=args["requested_tier"],
            project=args["project"],
        )

    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError:
        _audit(
            "router_result",
            project=args["project"],
            requested_tier=args["requested_tier"],
            status="failed",
            error_type="invalid_json",
        )
        return _error_result(
            "Central coder delegation returned invalid JSON.",
            requested_tier=args["requested_tier"],
            project=args["project"],
        )

    if not isinstance(response, dict):
        return _error_result(
            "Central coder delegation returned an invalid response.",
            requested_tier=args["requested_tier"],
            project=args["project"],
        )

    result = {
        **response,
        "ok": True,
        "project": args["project"],
        "task_type": args["task_type"],
        "complexity": args["complexity"],
        "risk": args["risk"],
        "mutation_policy": args["mutation_policy"],
        "requested_tier": args["requested_tier"],
        "selected_primary_model": response.get("selected_primary_model"),
        "actual_route": response.get("actual_route"),
        "attempted_routes": response.get("attempted_routes") or [],
        "mutation_started": bool(response.get("mutation_started")),
        "production_privileges": False,
    }

    _audit(
        "router_result",
        project=args["project"],
        requested_tier=args["requested_tier"],
        status=str(response.get("status", "submitted")),
        run_id=response.get("run_id"),
        task_id=response.get("task_id"),
        selected_primary_model=response.get("selected_primary_model"),
        actual_route=response.get("actual_route"),
        attempted_routes=response.get("attempted_routes") or [],
        mutation_started=bool(response.get("mutation_started")),
        production_privileges=False,
    )
    return _json_result(result)


def _contains_repository_reference(args: Any) -> bool:
    try:
        rendered = json.dumps(args, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        rendered = str(args)
    lowered = rendered.lower()
    return any(marker in lowered for marker in _REPOSITORY_MARKERS)


def _terminal_script_and_args(command: str) -> tuple[str, list[str]] | None:
    if not command.strip() or _SHELL_META_PATTERN.search(command):
        return None

    try:
        argv = shlex.split(command, posix=True)
    except ValueError:
        return None
    if not argv:
        return None

    if argv[0] in _CONTROLLER_POLICIES:
        return argv[0], argv[1:]

    if (
        argv[0] in _INTERPRETERS
        and len(argv) >= 2
        and argv[1] in _CONTROLLER_POLICIES
    ):
        return argv[1], argv[2:]

    return None


def _terminal_allowed(command: Any) -> bool:
    if not isinstance(command, str):
        return False

    parsed = _terminal_script_and_args(command)
    if parsed is None:
        return False

    script, argv = parsed
    if not argv:
        return False

    allowed_subcommands = _CONTROLLER_POLICIES[script]
    if allowed_subcommands is None:
        return True
    return argv[0] in allowed_subcommands


def _block(
    *,
    tool_name: str,
    reason: str,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
) -> dict[str, str]:
    _audit(
        "local_tool_rejected",
        tool_name=tool_name,
        reason=reason,
        task_id=task_id,
        session_id=session_id,
        tool_call_id=tool_call_id,
    )
    return {
        "action": "block",
        "message": f"{_BLOCK_MESSAGE} Reason: {reason}",
    }


def _on_pre_tool_call(
    tool_name: str = "",
    args: Any = None,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
    **_: Any,
) -> dict[str, str] | None:
    normalized_name = str(tool_name or "").strip()
    arguments = args if isinstance(args, Mapping) else {}

    if normalized_name == "coder_delegate":
        return None

    if normalized_name == "terminal":
        command = arguments.get("command")
        if _terminal_allowed(command):
            return None
        return _block(
            tool_name=normalized_name,
            reason=(
                "Kael terminal accepts only one simple invocation of "
                "monitorctl.py, opsctl.py, reconcilectl.py, runctl.py, or "
                "non-submit coderctl.py commands."
            ),
            task_id=task_id,
            session_id=session_id,
            tool_call_id=tool_call_id,
        )

    if normalized_name == "search_files":
        return _block(
            tool_name=normalized_name,
            reason="Generic local file search is disabled for Kael.",
            task_id=task_id,
            session_id=session_id,
            tool_call_id=tool_call_id,
        )

    if normalized_name in _CODE_EXECUTION_TOOLS:
        return _block(
            tool_name=normalized_name,
            reason="General code or shell execution is disabled for Kael.",
            task_id=task_id,
            session_id=session_id,
            tool_call_id=tool_call_id,
        )

    if _GITHUB_TOOL_PATTERN.search(normalized_name):
        return _block(
            tool_name=normalized_name,
            reason="Direct Git or GitHub tools are disabled for Kael.",
            task_id=task_id,
            session_id=session_id,
            tool_call_id=tool_call_id,
        )

    if normalized_name in _FILE_TOOLS and _contains_repository_reference(arguments):
        return _block(
            tool_name=normalized_name,
            reason="Direct access to a local project or coder workspace is disabled.",
            task_id=task_id,
            session_id=session_id,
            tool_call_id=tool_call_id,
        )

    return None


def _on_post_tool_call(
    tool_name: str = "",
    status: str = "",
    error_type: str | None = None,
    error_message: str | None = None,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
    **_: Any,
) -> None:
    if tool_name != "terminal" or status not in {"error", "blocked"}:
        return
    _audit(
        "terminal_failure",
        tool_name=tool_name,
        status=status,
        error_type=error_type,
        error_message=(error_message or "")[:500],
        task_id=task_id,
        session_id=session_id,
        tool_call_id=tool_call_id,
    )


def register(ctx: Any) -> None:
    ctx.register_tool(
        name="coder_delegate",
        toolset="kael-coder-control",
        schema=CODER_DELEGATE_SCHEMA,
        handler=_handle_coder_delegate,
        description=CODER_DELEGATE_SCHEMA["description"],
        emoji="🧭",
    )
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
