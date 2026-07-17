from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path


_POWERSHELL_NAMES = {
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
}
_MODEL_FLAGS = {"-m", "--model"}


def apply_codex_model(
    command: tuple[str, ...],
    model: str | None,
) -> tuple[str, ...]:
    """Override a user-level Codex model with a Supervisor-owned model.

    Codex reads ``~/.codex/config.toml`` before starting a task. A model selected
    there can belong to another provider, for example Amazon Bedrock, and then be
    rejected when the CLI is authenticated through a ChatGPT account. The command
    line model flag has higher priority and keeps Supervisor tasks independent from
    unrelated desktop/CLI profiles.
    """

    selected = (model or "").strip()
    if not command or not selected:
        return command

    values = list(command)
    for index, value in enumerate(values[:-1]):
        if value.casefold() in _MODEL_FLAGS:
            values[index + 1] = selected
            return tuple(values)

    try:
        exec_index = next(
            index for index, value in enumerate(values) if value.casefold() == "exec"
        )
    except StopIteration:
        # Supervisor only runs non-interactive ``codex exec`` tasks. Do not guess
        # where a global option belongs for an unrelated custom command.
        return command

    values[exec_index:exec_index] = ["--model", selected]
    return tuple(values)


def _wrap_batch_command(script: Path, arguments: tuple[str, ...]) -> tuple[str, ...]:
    command_line = subprocess.list2cmdline((str(script), *arguments))
    # npm installs Codex on Windows as a .cmd shim. Launch it through cmd.exe so
    # the trailing '-' used for stdin reaches Codex instead of being parsed as a
    # PowerShell parameter. Switching the code page also keeps Russian errors
    # readable in Supervisor and Telegram.
    return (
        "cmd.exe",
        "/d",
        "/s",
        "/c",
        f"chcp 65001>nul & call {command_line}",
    )


def normalize_codex_command(
    command: tuple[str, ...],
    *,
    is_windows: bool | None = None,
    which: Callable[[str], str | None] = shutil.which,
    path_exists: Callable[[Path], bool] = Path.exists,
) -> tuple[str, ...]:
    """Return a subprocess-safe Codex command for the current platform.

    npm creates codex.ps1 and codex.cmd on Windows. A command such as
    ``powershell.exe -File codex.ps1 exec ... -`` fails before Codex starts,
    because Windows PowerShell treats the final ``-`` as an invalid parameter
    name. The sibling .cmd shim accepts that argument and correctly forwards
    piped stdin to the Codex CLI.
    """

    if not command:
        return command
    windows = os.name == "nt" if is_windows is None else bool(is_windows)
    if not windows:
        return command

    executable_name = Path(command[0]).name.casefold()
    if executable_name in _POWERSHELL_NAMES:
        file_index = next(
            (
                index
                for index, value in enumerate(command[1:], start=1)
                if value.casefold() in {"-file", "-f"}
            ),
            None,
        )
        if file_index is None or file_index + 1 >= len(command):
            return command
        script = Path(os.path.expandvars(command[file_index + 1]))
        if script.name.casefold() != "codex.ps1":
            return command
        batch = script.with_suffix(".cmd")
        if not path_exists(batch):
            return command
        return _wrap_batch_command(batch, command[file_index + 2 :])

    resolved = which(command[0])
    target = Path(os.path.expandvars(resolved or command[0]))
    suffix = target.suffix.casefold()
    if suffix == ".ps1" and target.name.casefold() == "codex.ps1":
        batch = target.with_suffix(".cmd")
        if path_exists(batch):
            return _wrap_batch_command(batch, command[1:])
        return command
    if suffix in {".cmd", ".bat"}:
        return _wrap_batch_command(target, command[1:])
    return command


__all__ = ("apply_codex_model", "normalize_codex_command")
