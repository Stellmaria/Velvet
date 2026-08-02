from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path


PASSTHROUGH_VARIABLE = "GH_TOKEN"


class ConfigPatchError(RuntimeError):
    pass


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _meaningful(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped and not stripped.startswith("#"))


def _yaml_code(line: str) -> str:
    return line.split("#", 1)[0].rstrip()


def _find_top_level_section(lines: list[str], name: str) -> tuple[int, int] | None:
    marker = f"{name}:"
    for start, line in enumerate(lines):
        if _indent_width(line) == 0 and _yaml_code(line) == marker:
            for end in range(start + 1, len(lines)):
                candidate = lines[end]
                if _meaningful(candidate) and _indent_width(candidate) == 0:
                    return start, end
            return start, len(lines)
    return None


def _find_mapping_key(
    lines: list[str],
    *,
    start: int,
    end: int,
    name: str,
) -> int | None:
    for index in range(start + 1, end):
        line = lines[index]
        if _indent_width(line) != 2:
            continue
        key, separator, _value = _yaml_code(line).strip().partition(":")
        if separator and key == name:
            return index
    return None


def _normalize_scalar(value: str) -> str:
    return value.strip().strip('"').strip("'")


def config_has_mapping_scalar(text: str, section_name: str, key: str, value: str) -> bool:
    lines = text.splitlines()
    section = _find_top_level_section(lines, section_name)
    if section is None:
        return False
    start, end = section
    key_index = _find_mapping_key(lines, start=start, end=end, name=key)
    if key_index is None:
        return False
    suffix = _yaml_code(lines[key_index]).split(":", 1)[1]
    return _normalize_scalar(suffix) == value


def _ensure_mapping_scalar_lines(
    lines: list[str],
    *,
    section_name: str,
    key: str,
    rendered_value: str,
) -> bool:
    section = _find_top_level_section(lines, section_name)
    desired = f"  {key}: {rendered_value}"
    if section is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend((f"{section_name}:", desired))
        return True
    start, end = section
    key_index = _find_mapping_key(lines, start=start, end=end, name=key)
    if key_index is None:
        lines.insert(end, desired)
        return True
    if _yaml_code(lines[key_index]).strip() == desired.strip():
        return False
    lines[key_index] = desired
    return True


def _inline_values(suffix: str) -> list[str] | None:
    clean = suffix.strip()
    if not (clean.startswith("[") and clean.endswith("]")):
        return None
    body = clean[1:-1].strip()
    if not body:
        return []
    return [_normalize_scalar(item) for item in body.split(",")]


def config_has_env_passthrough(text: str, variable: str) -> bool:
    lines = text.splitlines()
    section = _find_top_level_section(lines, "terminal")
    if section is None:
        return False

    start, end = section
    key_index = _find_mapping_key(
        lines,
        start=start,
        end=end,
        name="env_passthrough",
    )
    if key_index is None:
        return False

    suffix = _yaml_code(lines[key_index]).split(":", 1)[1].strip()
    inline = _inline_values(suffix)
    if inline is not None:
        return variable in inline
    if suffix not in {"", "null", "~"}:
        return False

    for index in range(key_index + 1, end):
        line = lines[index]
        stripped = _yaml_code(line).strip()
        if stripped.startswith("-"):
            value = _normalize_scalar(stripped[1:])
            if value == variable:
                return True
            continue
        if _meaningful(line) and _indent_width(line) <= 2:
            break
    return False


def ensure_env_passthrough(path: Path, variable: str = PASSTHROUGH_VARIABLE) -> bool:
    if not path.is_file():
        raise ConfigPatchError(f"Отсутствует Hermes config: {path}")

    original = path.read_text(encoding="utf-8")
    if config_has_env_passthrough(original, variable):
        return False

    lines = original.splitlines()
    section = _find_top_level_section(lines, "terminal")

    if section is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(
            [
                "terminal:",
                "  env_passthrough:",
                f"    - {variable}",
            ]
        )
    else:
        start, end = section
        key_index = _find_mapping_key(
            lines,
            start=start,
            end=end,
            name="env_passthrough",
        )

        if key_index is None:
            lines[end:end] = [
                "  env_passthrough:",
                f"    - {variable}",
            ]
        else:
            suffix = _yaml_code(lines[key_index]).split(":", 1)[1].strip()
            inline = _inline_values(suffix)

            if inline is not None:
                values = [item for item in inline if item]
                values.append(variable)
                rendered = ", ".join(values)
                lines[key_index] = f"  env_passthrough: [{rendered}]"
            elif suffix in {"", "null", "~"}:
                block_end = end
                for index in range(key_index + 1, end):
                    line = lines[index]
                    stripped = _yaml_code(line).strip()
                    if stripped.startswith("-"):
                        continue
                    if _meaningful(line) and _indent_width(line) <= 2:
                        block_end = index
                        break
                lines[key_index] = "  env_passthrough:"
                lines.insert(block_end, f"    - {variable}")
            else:
                raise ConfigPatchError(
                    f"Неподдерживаемый terminal.env_passthrough в {path}: {suffix}"
                )

    updated = "\n".join(lines) + "\n"
    mode = stat.S_IMODE(path.stat().st_mode)
    path.write_text(updated, encoding="utf-8")
    os.chmod(path, mode)
    return True


def ensure_runtime_contract(path: Path, *, profile: str) -> bool:
    if profile not in {"coder", "kael"}:
        raise ConfigPatchError(f"Неизвестный Hermes runtime profile: {profile}")
    if not path.is_file():
        raise ConfigPatchError(f"Отсутствует Hermes config: {path}")

    original = path.read_text(encoding="utf-8")
    lines = original.splitlines()
    changed = False
    changed |= _ensure_mapping_scalar_lines(
        lines,
        section_name="terminal",
        key="cwd",
        rendered_value="/workspace" if profile == "coder" else "/opt/data",
    )
    changed |= _ensure_mapping_scalar_lines(
        lines,
        section_name="compression",
        key="enabled",
        rendered_value="true",
    )
    changed |= _ensure_mapping_scalar_lines(
        lines,
        section_name="tool_loop_guardrails",
        key="warnings_enabled",
        rendered_value="true",
    )
    changed |= _ensure_mapping_scalar_lines(
        lines,
        section_name="tool_loop_guardrails",
        key="hard_stop_enabled",
        rendered_value="true",
    )

    updated = "\n".join(lines).rstrip() + "\n"
    if updated != original:
        mode = stat.S_IMODE(path.stat().st_mode)
        path.write_text(updated, encoding="utf-8")
        os.chmod(path, mode)
        changed = True
    if profile == "coder":
        changed = ensure_env_passthrough(path) or changed
    return changed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Patch fixed Hermes runtime contracts")
    parser.add_argument(
        "--profile",
        choices=("coder", "kael"),
        default="coder",
    )
    parser.add_argument("paths", nargs="+")
    return parser


def main(argv: list[str]) -> int:
    args = _parser().parse_args(argv[1:])
    for raw_path in args.paths:
        path = Path(raw_path)
        changed = ensure_runtime_contract(path, profile=args.profile)
        state = "updated" if changed else "already configured"
        print(f"Hermes {args.profile} runtime config {state}: {path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (ConfigPatchError, PermissionError) as exc:
        print(f"Hermes runtime config patch failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
