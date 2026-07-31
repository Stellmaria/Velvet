from __future__ import annotations

import sys
from pathlib import Path


PASSTHROUGH_VARIABLE = "GH_TOKEN"


class ConfigPatchError(RuntimeError):
    pass


def _block_end(lines: list[str], start: int) -> int:
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line and not line.startswith((" ", "\t", "#")):
            return index
    return len(lines)


def ensure_env_passthrough(path: Path) -> bool:
    if not path.is_file():
        raise ConfigPatchError(f"Отсутствует Hermes config: {path}")

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    try:
        terminal_index = next(
            index for index, line in enumerate(lines) if line.rstrip() == "terminal:"
        )
    except StopIteration:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(
            [
                "terminal:",
                "  env_passthrough:",
                f"    - {PASSTHROUGH_VARIABLE}",
            ]
        )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True

    terminal_end = _block_end(lines, terminal_index)
    env_index: int | None = None

    for index in range(terminal_index + 1, terminal_end):
        if lines[index].strip().startswith("env_passthrough:"):
            env_index = index
            break

    if env_index is None:
        lines[terminal_index + 1:terminal_index + 1] = [
            "  env_passthrough:",
            f"    - {PASSTHROUGH_VARIABLE}",
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True

    env_line = lines[env_index]
    suffix = env_line.split(":", 1)[1].strip()

    if PASSTHROUGH_VARIABLE in suffix:
        return False

    if suffix in {"", "[]", "null", "~"}:
        lines[env_index] = "  env_passthrough:"
        lines.insert(env_index + 1, f"    - {PASSTHROUGH_VARIABLE}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True

    env_end = terminal_end
    for index in range(env_index + 1, terminal_end):
        line = lines[index]
        if line.startswith("  ") and not line.startswith("    ") and line.strip():
            env_end = index
            break

    for line in lines[env_index + 1:env_end]:
        if line.strip() == f"- {PASSTHROUGH_VARIABLE}":
            return False

    lines.insert(env_end, f"    - {PASSTHROUGH_VARIABLE}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        raise ConfigPatchError("Укажите хотя бы один config.yaml")

    for raw_path in argv[1:]:
        path = Path(raw_path)
        changed = ensure_env_passthrough(path)
        state = "updated" if changed else "already configured"
        print(f"Hermes config {state}: {path}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except ConfigPatchError as exc:
        print(f"Hermes config patch failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
