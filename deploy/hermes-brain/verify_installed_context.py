from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path
from typing import Any


class RuntimeContextError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_private_readable(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise RuntimeContextError(f"Context file отсутствует или небезопасен: {path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o022:
        raise RuntimeContextError(f"Context file доступен для записи группе/всем: {path}")


def _output_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list):
        raise RuntimeContextError("Context manifest не содержит outputs")
    result: dict[str, dict[str, Any]] = {}
    for record in outputs:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise RuntimeContextError("Context manifest содержит неверный output")
        result[record["path"]] = record
    return result


def _verify_hash(path: Path, record: dict[str, Any]) -> None:
    _require_private_readable(path)
    if record.get("sha256") != _sha256(path) or record.get("bytes") != path.stat().st_size:
        raise RuntimeContextError(f"Context hash/size mismatch: {path}")


def verify_installed(target: Path, *, entity: str, mode: str) -> dict[str, Any]:
    if target.is_symlink():
        raise RuntimeContextError(f"Runtime context target не может быть symlink: {target}")
    target = target.resolve()
    manifest_path = target / "context-manifest.json"
    _require_private_readable(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeContextError("Installed context manifest повреждён") from error
    if manifest.get("entity_id") != entity:
        raise RuntimeContextError(
            f"Context entity mismatch: expected={entity}, actual={manifest.get('entity_id')}"
        )
    if mode not in {"hermes", "codex"}:
        raise RuntimeContextError(f"Неизвестный runtime mode: {mode}")
    outputs = _output_map(manifest)
    if mode == "hermes":
        mappings = {"SOUL.md": target / "SOUL.md", "AGENTS.md": target / "AGENTS.md"}
        skill_prefix = target / "skills"
    else:
        mappings = {
            "CODEX.AGENTS.md": target / "AGENTS.md",
            "output.schema.json": target / "output.schema.json",
        }
        skill_prefix = target / ".agents" / "skills"
    for output_name, installed in mappings.items():
        record = outputs.get(output_name)
        if record is None:
            raise RuntimeContextError(f"Context manifest не содержит {output_name}")
        _verify_hash(installed, record)
    for output_name, record in outputs.items():
        if output_name.startswith("skills/"):
            relative = Path(output_name).relative_to("skills")
            _verify_hash(skill_prefix / relative, record)

    agents_path = target / "AGENTS.md"
    text = agents_path.read_text(encoding="utf-8")
    for sentinel in (
        f"Entity ID: `{entity}`",
        f"Project scope: `{manifest.get('project')}`",
        "Context protocol: `velvet-brain/v1`",
    ):
        if sentinel not in text:
            raise RuntimeContextError(f"В active AGENTS.md отсутствует sentinel: {sentinel}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify installed Velvet Brain context")
    parser.add_argument("--target", required=True)
    parser.add_argument("--entity", required=True)
    parser.add_argument("--mode", choices=("hermes", "codex"), required=True)
    args = parser.parse_args()
    manifest = verify_installed(
        Path(args.target),
        entity=args.entity,
        mode=args.mode,
    )
    print(f"Installed context verified: {manifest['entity_id']} ({args.mode})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeContextError, ValueError) as error:
        print(f"Installed context verification failed: {error}", file=sys.stderr)
        raise SystemExit(2)
