from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from context_compiler import BrainError, verify_pack


SKILL_NAME = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
MANAGED_SKILLS = ".velvet-brain-managed.json"


class InstallError(RuntimeError):
    pass


def _atomic_copy(source: Path, target: Path, *, uid: int, gid: int, mode: int) -> None:
    if not source.is_file() or source.is_symlink():
        raise InstallError(f"Отсутствует безопасный source: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(source.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        os.chown(temporary, uid, gid)
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _chown_tree(root: Path, uid: int, gid: int) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        os.chown(path, uid, gid)
        os.chmod(path, 0o700 if path.is_dir() else 0o600)
    os.chown(root, uid, gid)
    os.chmod(root, 0o700)


def _load_managed_skills(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise InstallError(f"Повреждён managed skills manifest: {path}") from error
    if not isinstance(value, list) or not all(
        isinstance(item, str) and SKILL_NAME.fullmatch(item) for item in value
    ):
        raise InstallError(f"Некорректный managed skills manifest: {path}")
    return set(value)


def _install_skills(source_root: Path, target_root: Path, *, uid: int, gid: int) -> None:
    for candidate in (target_root.parent, target_root):
        if candidate.is_symlink():
            raise InstallError(f"Symlink запрещён в skill target: {candidate}")
    target_root.mkdir(parents=True, exist_ok=True)
    if target_root.parent.name == ".agents":
        os.chown(target_root.parent, uid, gid)
        os.chmod(target_root.parent, 0o700)
    manifest_path = target_root / MANAGED_SKILLS
    previous = _load_managed_skills(manifest_path)
    current = (
        {
            path.name
            for path in source_root.iterdir()
            if path.is_dir() and SKILL_NAME.fullmatch(path.name)
        }
        if source_root.is_dir()
        else set()
    )
    for skill_name in sorted(previous | current):
        target = target_root / skill_name
        if target.exists():
            if target.is_symlink() or not target.is_dir():
                raise InstallError(f"Skill target небезопасен: {target}")
            shutil.rmtree(target)
        if skill_name in current:
            shutil.copytree(source_root / skill_name, target)
            _chown_tree(target, uid, gid)
    payload = (json.dumps(sorted(current), ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    fd, temporary = tempfile.mkstemp(prefix=".managed-skills.", dir=target_root)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.chown(temporary, uid, gid)
        os.chmod(temporary, 0o600)
        os.replace(temporary, manifest_path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    os.chown(target_root, uid, gid)
    os.chmod(target_root, 0o700)


def install_pack(pack: Path, target: Path, *, entity: str, mode: str) -> dict[str, object]:
    manifest = verify_pack(pack, expected_entity=entity)
    if mode not in {"hermes", "codex"}:
        raise InstallError(f"Неизвестный install mode: {mode}")
    if not target.is_dir() or target.is_symlink():
        raise InstallError(f"Target должен быть существующим каталогом: {target}")
    uid = target.stat().st_uid
    gid = target.stat().st_gid

    if mode == "hermes":
        _atomic_copy(pack / "SOUL.md", target / "SOUL.md", uid=uid, gid=gid, mode=0o600)
        _atomic_copy(pack / "AGENTS.md", target / "AGENTS.md", uid=uid, gid=gid, mode=0o600)
        for seed_name, runtime_name in (
            ("MEMORY.seed.md", "MEMORY.md"),
            ("USER.seed.md", "USER.md"),
        ):
            source = pack / seed_name
            destination = target / runtime_name
            if source.is_file() and (
                not destination.exists() or destination.stat().st_size == 0
            ):
                _atomic_copy(source, destination, uid=uid, gid=gid, mode=0o600)
        skills_target = target / "skills"
    else:
        _atomic_copy(
            pack / "CODEX.AGENTS.md",
            target / "AGENTS.md",
            uid=uid,
            gid=gid,
            mode=0o600,
        )
        _atomic_copy(
            pack / "output.schema.json",
            target / "output.schema.json",
            uid=uid,
            gid=gid,
            mode=0o600,
        )
        brain = target / "brain"
        if brain.is_symlink():
            raise InstallError(f"Symlink запрещён в brain target: {brain}")
        brain.mkdir(parents=True, exist_ok=True)
        os.chown(brain, uid, gid)
        os.chmod(brain, 0o700)
        for name in ("SOUL.md", "MEMORY.seed.md", "USER.seed.md"):
            source = pack / name
            if source.is_file():
                _atomic_copy(source, brain / name, uid=uid, gid=gid, mode=0o600)
        skills_target = target / ".agents" / "skills"

    _install_skills(pack / "skills", skills_target, uid=uid, gid=gid)
    _atomic_copy(
        pack / "context-manifest.json",
        target / "context-manifest.json",
        uid=uid,
        gid=gid,
        mode=0o600,
    )
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install a verified Velvet Brain pack")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--entity", required=True)
    parser.add_argument("--mode", required=True, choices=("hermes", "codex"))
    return parser


def main() -> int:
    args = _parser().parse_args()
    manifest = install_pack(
        Path(args.pack),
        Path(args.target),
        entity=args.entity,
        mode=args.mode,
    )
    print(
        f"Context pack installed: {manifest['entity_id']} -> "
        f"{Path(args.target).resolve()}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BrainError, InstallError, OSError, ValueError) as error:
        print(f"Velvet Brain installation failed: {error}", file=sys.stderr)
        raise SystemExit(2)
