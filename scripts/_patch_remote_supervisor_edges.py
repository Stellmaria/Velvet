from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "velvet_supervisor/bootstrap.py"
CONSOLE = ROOT / "velvet_bot/handlers/supervisor_console.py"
REMOTE = ROOT / "velvet_supervisor/remote_console.py"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: ожидалось одно совпадение, найдено {count}")
    return source.replace(old, new, 1)


def main() -> None:
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    bootstrap = replace_once(
        bootstrap,
        '        "/SD",\n        start_at.strftime("%m/%d/%Y"),\n',
        "",
        "locale-independent schtasks date",
    )
    ast.parse(bootstrap, filename=str(BOOTSTRAP))
    BOOTSTRAP.write_text(bootstrap, encoding="utf-8")

    console = CONSOLE.read_text(encoding="utf-8")
    console = replace_once(
        console,
        "                requested_by=_requested_by(callback.message),\n",
        "                requested_by=(\n"
        "                    f\"{callback.from_user.id}:@\"\n"
        "                    f\"{callback.from_user.username or 'без_username'}\"\n"
        "                ),\n",
        "callback owner identity",
    )
    ast.parse(console, filename=str(CONSOLE))
    CONSOLE.write_text(console, encoding="utf-8")

    remote = REMOTE.read_text(encoding="utf-8")
    remote = replace_once(
        remote,
        're.compile(r"[\\x00-\\x1f;&|><`]|$\\(")',
        're.compile(r"[\\x00-\\x1f;&|><`]|\\$\\(")',
        "powershell substitution guard",
    )
    ast.parse(remote, filename=str(REMOTE))
    REMOTE.write_text(remote, encoding="utf-8")


if __name__ == "__main__":
    main()
