from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_MANIFEST = Path("brain-vault/manifest.json")
MAX_TEXT_BYTES = 256_000
MAX_ENTITY_CONTEXT_BYTES = 128_000
ENTITY_ID = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
ISO_DATE = re.compile(r"^20\d{2}-\d{2}-\d{2}$")
FRONTMATTER_TYPES = {"entity", "index", "policy", "project"}
SENSITIVITY_LEVELS = {"public", "internal", "restricted"}
REQUIRED_FRONTMATTER = {
    "id",
    "type",
    "scope",
    "status",
    "owner",
    "sensitivity",
    "version",
    "updated",
}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
    re.compile(
        r"(?im)^\s*(?:api[_-]?key|token|password|secret|authorization)\s*[:=]\s*"
        r"(?!\$\{|<|replace_|\[redacted\]|none\b)[^\s#]{16,}\s*$"
    ),
)


class BrainError(RuntimeError):
    pass


@dataclass(frozen=True)
class Source:
    path: str
    content: str
    sha256: str
    bytes: int


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).rstrip()
        + "\n"
    ).encode("utf-8")


def _inside(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def resolve_file(root: Path, relative: str, *, suffixes: set[str] | None = None) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise BrainError(f"Недопустимый source path: {relative}")
    unresolved = root / candidate
    current = root
    for part in candidate.parts:
        current /= part
        if current.is_symlink():
            raise BrainError(f"Symlink запрещён в source path: {relative}")
    path = unresolved.resolve()
    if not _inside(root, path) or not path.is_file():
        raise BrainError(f"Source отсутствует либо выходит за repository root: {relative}")
    if suffixes is not None and path.suffix.lower() not in suffixes:
        raise BrainError(f"Неподдерживаемый тип source: {relative}")
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise BrainError(f"Source превышает {MAX_TEXT_BYTES} bytes: {relative}")
    return path


def scan_for_secrets(text: str, *, source: str) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            raise BrainError(f"В {source} найден secret-like материал")


def _frontmatter_values(text: str, *, source: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise BrainError(f"В {source} отсутствует YAML frontmatter")
    values: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip()] = value.strip().strip('"').strip("'")
    else:
        raise BrainError(f"В {source} не закрыт YAML frontmatter")
    return values


def _parse_frontmatter(text: str, *, source: str) -> dict[str, str]:
    values = _frontmatter_values(text, source=source)
    missing = sorted(REQUIRED_FRONTMATTER - values.keys())
    if missing:
        raise BrainError(f"В {source} отсутствуют поля frontmatter: {', '.join(missing)}")
    return values


def _vault_markdown_requires_frontmatter(path: Path) -> bool:
    if path.name in {"README.md", "SKILL.md"}:
        return False
    if path.name.endswith(".seed.md"):
        return False
    return True


def validate_vault(repository_root: Path) -> list[str]:
    vault = (repository_root / "brain-vault").resolve()
    if not vault.is_dir() or not _inside(repository_root, vault):
        raise BrainError("Отсутствует brain-vault")
    checked: list[str] = []
    document_ids: dict[str, str] = {}
    for path in sorted(vault.rglob("*")):
        if path.is_dir():
            continue
        if path.is_symlink():
            raise BrainError(f"Symlink запрещён в brain-vault: {path.relative_to(repository_root)}")
        relative = path.relative_to(repository_root).as_posix()
        if path.stat().st_size > MAX_TEXT_BYTES:
            raise BrainError(f"Vault file слишком большой: {relative}")
        if path.suffix.lower() == ".json":
            try:
                text = path.read_text(encoding="utf-8")
                scan_for_secrets(text, source=relative)
                json.loads(text)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise BrainError(f"Некорректный JSON в {relative}: {error}") from error
        elif path.suffix.lower() == ".md":
            text = path.read_text(encoding="utf-8")
            scan_for_secrets(text, source=relative)
            if path.name == "SKILL.md":
                metadata = _frontmatter_values(text, source=relative)
                missing = sorted(
                    {"name", "description", "version", "author"} - metadata.keys()
                )
                if missing:
                    raise BrainError(
                        f"В {relative} отсутствуют skill fields: {', '.join(missing)}"
                    )
                if metadata["name"] != path.parent.name:
                    raise BrainError(f"Skill name/path mismatch в {relative}")
            elif _vault_markdown_requires_frontmatter(path):
                metadata = _parse_frontmatter(text, source=relative)
                document_id = metadata["id"]
                if not ENTITY_ID.fullmatch(document_id):
                    raise BrainError(f"Некорректный frontmatter id в {relative}")
                if document_id in document_ids:
                    raise BrainError(
                        f"Дублирующийся frontmatter id {document_id}: "
                        f"{document_ids[document_id]} и {relative}"
                    )
                if metadata["type"] not in FRONTMATTER_TYPES:
                    raise BrainError(f"Некорректный frontmatter type в {relative}")
                if metadata["status"] not in {"active", "deprecated", "draft"}:
                    raise BrainError(f"Некорректный frontmatter status в {relative}")
                if metadata["sensitivity"] not in SENSITIVITY_LEVELS:
                    raise BrainError(f"Некорректная sensitivity в {relative}")
                if not metadata["version"].isdigit() or int(metadata["version"]) < 1:
                    raise BrainError(f"Некорректная version в {relative}")
                if not ISO_DATE.fullmatch(metadata["updated"]):
                    raise BrainError(f"Некорректная updated date в {relative}")
                document_ids[document_id] = relative
        elif path.name != ".gitignore":
            raise BrainError(f"Неподдерживаемый файл в brain-vault: {relative}")
        checked.append(relative)
    return checked


def load_manifest(repository_root: Path, manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    path = resolve_file(repository_root, manifest_path.as_posix(), suffixes={".json"})
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise BrainError(f"Некорректный brain manifest: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise BrainError(f"Поддерживается brain manifest schema_version={SCHEMA_VERSION}")
    if not isinstance(manifest.get("brain_version"), int) or manifest["brain_version"] < 1:
        raise BrainError("Brain manifest не содержит положительный brain_version")
    entities = manifest.get("entities")
    if not isinstance(entities, dict) or not entities:
        raise BrainError("Brain manifest не содержит entities")
    for entity_id, entity in entities.items():
        if not isinstance(entity_id, str) or ENTITY_ID.fullmatch(entity_id) is None:
            raise BrainError(f"Некорректный entity id: {entity_id!r}")
        if not isinstance(entity, dict):
            raise BrainError(f"Некорректный entity record: {entity_id}")
        for key in ("runtime", "project", "soul"):
            if not isinstance(entity.get(key), str) or not entity[key].strip():
                raise BrainError(f"Entity {entity_id} не содержит строковый {key}")
        if not isinstance(entity["agents"], list) or not all(
            isinstance(item, str) for item in entity["agents"]
        ) or not entity["agents"]:
            raise BrainError(
                f"Entity {entity_id} agents должен быть непустым списком paths"
            )
        skills = entity.get("skills", [])
        if not isinstance(skills, list) or not all(isinstance(item, str) for item in skills):
            raise BrainError(f"Entity {entity_id} skills должен быть списком paths")
        artifacts = entity.get("artifacts", {})
        if not isinstance(artifacts, dict) or not all(
            isinstance(target, str) and isinstance(source, str)
            for target, source in artifacts.items()
        ):
            raise BrainError(f"Entity {entity_id} artifacts должен быть mapping paths")
        if (
            "openai-codex" in entity["runtime"]
            and "output.schema.json" not in artifacts
        ):
            raise BrainError(f"Codex entity {entity_id} не содержит output.schema.json")
        for target in artifacts:
            target_path = Path(target)
            if (
                target_path.is_absolute()
                or ".." in target_path.parts
                or len(target_path.parts) != 1
                or target_path.suffix.lower() not in {".json", ".md"}
            ):
                raise BrainError(f"Некорректный artifact target для {entity_id}: {target}")
        declared = [
            item
            for key in ("soul", "memory_seed", "user_seed")
            if isinstance((item := entity.get(key)), str) and item
        ] + entity["agents"] + skills + list(artifacts.values())
        if len(declared) != len(set(declared)):
            raise BrainError(f"Entity {entity_id} содержит повторяющиеся sources")
        for source in declared:
            resolve_file(repository_root, source, suffixes={".md", ".json"})
        forbidden_sources = {
            "velvet-coder": {
                "deploy/hermes-coders/SOUL.max.md",
                "deploy/hermes-coders/AGENTS.max.md",
                "brain-vault/entities/max-coder.md",
                "brain-vault/projects/max.md",
                "brain-vault/memory/max-coder.seed.md",
            },
            "max-coder": {
                "deploy/hermes-coders/SOUL.velvet.md",
                "deploy/hermes-coders/AGENTS.velvet.md",
                "brain-vault/entities/velvet-coder.md",
                "brain-vault/projects/velvet.md",
                "brain-vault/memory/velvet-coder.seed.md",
            },
        }.get(entity_id, set())
        for source in declared:
            if source in forbidden_sources:
                raise BrainError(f"Cross-project source запрещён для {entity_id}: {source}")
        if entity_id == "velvet-librarian" and any(
            entity.get(key) for key in ("memory_seed", "user_seed", "skills")
        ):
            raise BrainError("Velvet Librarian не может получать memory, user seed или skills")
    return manifest


def _read_source(
    repository_root: Path,
    relative: str,
    *,
    suffixes: set[str] | None = None,
) -> Source:
    path = resolve_file(repository_root, relative, suffixes=suffixes or {".md"})
    raw = path.read_bytes()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BrainError(f"Source должен быть UTF-8: {relative}") from error
    scan_for_secrets(content, source=relative)
    return Source(relative, content.rstrip() + "\n", _sha256(raw), len(raw))


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.chmod(path, 0o640)


def _render_agents(entity_id: str, entity: dict[str, Any], sources: list[Source]) -> bytes:
    header = (
        "# Compiled Entity Context\n\n"
        "Этот файл детерминированно собран из Velvet Brain Vault. "
        "Не редактируй runtime-копию вручную.\n\n"
        f"- Context protocol: `velvet-brain/v{SCHEMA_VERSION}`\n"
        f"- Entity ID: `{entity_id}`\n"
        f"- Project scope: `{entity['project']}`\n"
        f"- Runtime: `{entity['runtime']}`\n"
    )
    sections = [header.rstrip()]
    for source in sources:
        sections.append(f"## Source: `{source.path}`\n\n{source.content.rstrip()}")
    return ("\n\n---\n\n".join(sections).rstrip() + "\n").encode("utf-8")


def _render_codex_agents(
    entity_id: str,
    entity: dict[str, Any],
    *,
    soul: Source | None,
    agents: list[Source],
    memory: Source | None,
    user: Source | None,
) -> bytes:
    selected = [source for source in (soul, *agents, memory, user) if source is not None]
    header = (
        "# Compiled Codex Entity Context\n\n"
        "Этот global AGENTS.md детерминированно собран из Velvet Brain Vault. "
        "Не редактируй runtime-копию вручную.\n\n"
        f"- Context protocol: `velvet-brain/v{SCHEMA_VERSION}`\n"
        f"- Entity ID: `{entity_id}`\n"
        f"- Project scope: `{entity['project']}`\n"
        "- Instruction root: `$CODEX_HOME/AGENTS.md`\n"
    )
    sections = [header.rstrip()]
    for source in selected:
        sections.append(f"## Source: `{source.path}`\n\n{source.content.rstrip()}")
    return ("\n\n---\n\n".join(sections).rstrip() + "\n").encode("utf-8")


def _copy_skill(repository_root: Path, skill_file: str, output: Path) -> list[Path]:
    source_file = resolve_file(repository_root, skill_file, suffixes={".md"})
    if source_file.name != "SKILL.md":
        raise BrainError(f"Skill source должен называться SKILL.md: {skill_file}")
    source_dir = source_file.parent
    skill_name = source_dir.name
    if ENTITY_ID.fullmatch(skill_name) is None:
        raise BrainError(f"Некорректное имя skill directory: {skill_name}")
    target_dir = output / "skills" / skill_name
    copied: list[Path] = []
    for path in sorted(source_dir.rglob("*")):
        if path.is_dir():
            continue
        if path.is_symlink() or not _inside(source_dir, path.resolve()):
            raise BrainError(f"Skill symlink/path escape запрещён: {path}")
        if path.suffix.lower() not in {".md", ".json"}:
            raise BrainError(f"Skill содержит неподдерживаемый файл: {path}")
        raw = path.read_bytes()
        if len(raw) > MAX_TEXT_BYTES:
            raise BrainError(f"Skill file слишком большой: {path}")
        try:
            scan_for_secrets(raw.decode("utf-8"), source=str(path))
        except UnicodeDecodeError as error:
            raise BrainError(f"Skill file должен быть UTF-8: {path}") from error
        target = target_dir / path.relative_to(source_dir)
        _write_private(target, raw)
        copied.append(target)
    return copied


def _output_record(output_root: Path, path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {
        "path": path.relative_to(output_root).as_posix(),
        "sha256": _sha256(raw),
        "bytes": len(raw),
    }


def _enforce_context_budget(
    entity_id: str,
    paths: list[Path],
    *,
    label: str,
) -> None:
    size = sum(path.stat().st_size for path in paths if path.is_file())
    if size > MAX_ENTITY_CONTEXT_BYTES:
        raise BrainError(
            f"{label} context для {entity_id} превышает "
            f"{MAX_ENTITY_CONTEXT_BYTES} bytes: {size}"
        )


def compile_entity(
    repository_root: Path,
    entity_id: str,
    output: Path,
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    validate_vault(repository_root)
    manifest = load_manifest(repository_root, manifest_path)
    entity = manifest["entities"].get(entity_id)
    if not isinstance(entity, dict):
        raise BrainError(f"Неизвестная сущность: {entity_id}")
    output = output.resolve()
    if output.exists():
        if not output.is_dir() or output.is_symlink() or any(output.iterdir()):
            raise BrainError(f"Compile output должен быть пустым каталогом: {output}")
    output.mkdir(parents=True, exist_ok=True)
    os.chmod(output, 0o750)

    source_records: list[Source] = []
    soul: Source | None = None
    soul_path = entity.get("soul")
    if isinstance(soul_path, str) and soul_path:
        soul = _read_source(repository_root, soul_path)
        source_records.append(soul)
        _write_private(output / "SOUL.md", soul.content.encode("utf-8"))

    agent_sources = [_read_source(repository_root, item) for item in entity["agents"]]
    source_records.extend(agent_sources)
    _write_private(output / "AGENTS.md", _render_agents(entity_id, entity, agent_sources))

    seed_sources: dict[str, Source] = {}
    for key, target_name in (
        ("memory_seed", "MEMORY.seed.md"),
        ("user_seed", "USER.seed.md"),
    ):
        source_path = entity.get(key)
        if isinstance(source_path, str) and source_path:
            source = _read_source(repository_root, source_path)
            source_records.append(source)
            seed_sources[key] = source
            _write_private(output / target_name, source.content.encode("utf-8"))

    if "openai-codex" in str(entity["runtime"]):
        _write_private(
            output / "CODEX.AGENTS.md",
            _render_codex_agents(
                entity_id,
                entity,
                soul=soul,
                agents=agent_sources,
                memory=seed_sources.get("memory_seed"),
                user=seed_sources.get("user_seed"),
            ),
        )

    skill_files: list[Path] = []
    for skill in entity.get("skills", []):
        source = _read_source(repository_root, skill)
        source_records.append(source)
        skill_files.extend(_copy_skill(repository_root, skill, output))

    for target_name, source_path in sorted(entity.get("artifacts", {}).items()):
        source = _read_source(repository_root, source_path, suffixes={".json", ".md"})
        source_records.append(source)
        _write_private(output / target_name, source.content.encode("utf-8"))

    _enforce_context_budget(
        entity_id,
        [
            output / "SOUL.md",
            output / "AGENTS.md",
            output / "MEMORY.seed.md",
            output / "USER.seed.md",
        ],
        label="Hermes",
    )
    if (output / "CODEX.AGENTS.md").is_file():
        _enforce_context_budget(
            entity_id,
            [output / "CODEX.AGENTS.md"],
            label="Codex",
        )

    generated = sorted(
        [path for path in output.rglob("*") if path.is_file()],
        key=lambda path: path.relative_to(output).as_posix(),
    )
    compiled_manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "brain_id": manifest.get("brain_id", "velvet-brain"),
        "brain_version": manifest.get("brain_version", 1),
        "entity_id": entity_id,
        "project": entity["project"],
        "runtime": entity["runtime"],
        "sources": [
            {
                "path": source.path,
                "sha256": source.sha256,
                "bytes": source.bytes,
            }
            for source in source_records
        ],
        "outputs": [_output_record(output, path) for path in generated],
        "skills": sorted(path.parent.name for path in skill_files if path.name == "SKILL.md"),
    }
    _write_private(output / "context-manifest.json", _json_bytes(compiled_manifest))
    return compiled_manifest


def verify_pack(pack: Path, *, expected_entity: str | None = None) -> dict[str, Any]:
    pack = pack.resolve()
    manifest_path = pack / "context-manifest.json"
    if not manifest_path.is_file():
        raise BrainError(f"Pack не содержит context-manifest.json: {pack}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise BrainError(f"Некорректный context manifest: {error}") from error
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise BrainError("Неподдерживаемая версия context pack")
    if expected_entity is not None and manifest.get("entity_id") != expected_entity:
        raise BrainError(
            f"Ожидалась сущность {expected_entity}, получена {manifest.get('entity_id')}"
        )
    for record in manifest.get("outputs", []):
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise BrainError("Некорректная запись output в context manifest")
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise BrainError(f"Некорректный output path: {relative}")
        path = (pack / relative).resolve()
        if not _inside(pack, path) or not path.is_file():
            raise BrainError(f"Compiled output отсутствует: {relative}")
        raw = path.read_bytes()
        if record.get("sha256") != _sha256(raw) or record.get("bytes") != len(raw):
            raise BrainError(f"Hash/size mismatch для {relative}")
    expected = {
        str(record["path"])
        for record in manifest.get("outputs", [])
        if isinstance(record, dict) and isinstance(record.get("path"), str)
    }
    actual: set[str] = set()
    for path in pack.rglob("*"):
        if path.is_dir():
            continue
        if path.is_symlink():
            raise BrainError(f"Symlink запрещён в context pack: {path}")
        relative = path.relative_to(pack).as_posix()
        if relative != "context-manifest.json":
            actual.add(relative)
    if actual != expected:
        raise BrainError(
            "Context pack содержит неожиданные/отсутствующие files: "
            f"expected={sorted(expected)}, actual={sorted(actual)}"
        )
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Velvet Brain Vault compiler")
    parser.add_argument(
        "--repository-root",
        default=str(Path(__file__).resolve().parents[2]),
        help="Velvet repository root",
    )
    parser.add_argument(
        "--manifest",
        default=DEFAULT_MANIFEST.as_posix(),
        help="Repository-relative brain manifest",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("--entity", required=True)
    compile_parser.add_argument("--output", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--pack", required=True)
    verify_parser.add_argument("--entity")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(args.repository_root).resolve()
    manifest_path = Path(args.manifest)
    if args.command == "validate":
        files = validate_vault(root)
        manifest = load_manifest(root, manifest_path)
        print(
            f"Velvet Brain Vault: OK ({len(manifest['entities'])} entities, "
            f"{len(files)} files)"
        )
        return 0
    if args.command == "compile":
        compiled = compile_entity(
            root,
            args.entity,
            Path(args.output),
            manifest_path=manifest_path,
        )
        print(
            f"Context pack compiled: {compiled['entity_id']} -> "
            f"{Path(args.output).resolve()}"
        )
        return 0
    verified = verify_pack(Path(args.pack), expected_entity=args.entity)
    print(f"Context pack verified: {verified['entity_id']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BrainError, OSError, ValueError) as error:
        print(f"Velvet Brain error: {error}", file=sys.stderr)
        raise SystemExit(2)
