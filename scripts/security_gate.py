from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
LOCK_FILES = (ROOT / "requirements.lock", ROOT / "requirements-dev.lock")
EXCEPTIONS_FILE = ROOT / ".github" / "security-exceptions.json"

ACTION_USE_RE = re.compile(
    r"^\s*uses:\s*(?P<value>[^#\s]+)(?:\s+#\s*(?P<comment>.+))?\s*$"
)
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HASH_RE = re.compile(r"--hash=sha256:[0-9a-f]{64}\b")
PACKAGE_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==")
SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Telegram bot token", re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b")),
    (
        "assigned secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[=:]\s*[\"']?"
            r"(?!test(?:_|-)|example(?:_|-)|dummy(?:_|-)|ci(?:_|-))[A-Za-z0-9_./+=-]{24,}"
        ),
    ),
)
SECRET_EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
}
SECRET_EXCLUDED_PREFIXES = (
    "tests/fixtures/security/",
    ".env.example",
    ".env.server.example",
    ".env.hermes.example",
    ".env.vision-local.example",
)
ALLOWED_PR_WRITE_PERMISSIONS = {"security-events"}
ALLOWED_ARTIFACT_PATH_FRAGMENTS = (
    "output.txt",
    "metadata.json",
    "sbom",
    "generated-locks",
    "maintenance-changed-files.txt",
    "maintenance-diff-stat.txt",
    "maintenance-test-output.txt",
)


def _relative(path: Path, root: Path = ROOT) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _workflow_paths(root: Path = ROOT) -> tuple[Path, ...]:
    directory = root / ".github" / "workflows"
    return tuple(sorted((*directory.glob("*.yml"), *directory.glob("*.yaml"))))


def _top_level_permissions(source: str) -> dict[str, str]:
    lines = source.splitlines()
    result: dict[str, str] = {}
    for index, line in enumerate(lines):
        if line.rstrip() != "permissions:":
            continue
        for nested in lines[index + 1 :]:
            if nested and not nested.startswith((" ", "\t")):
                break
            match = re.match(r"^\s{2}([A-Za-z0-9_-]+):\s*([A-Za-z]+)\s*$", nested)
            if match:
                result[match.group(1)] = match.group(2)
        break
    return result


def check_action_pins(paths: Sequence[Path] | None = None, *, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    workflow_paths = tuple(paths) if paths is not None else _workflow_paths(root)
    for path in workflow_paths:
        source = path.read_text(encoding="utf-8")
        relative = _relative(path, root)
        if "permissions:" not in source:
            errors.append(f"{relative}: workflow must declare explicit permissions")
        if "pull_request_target:" in source:
            errors.append(f"{relative}: pull_request_target is forbidden")
        if "pull_request:" in source and "${{ secrets." in source:
            errors.append(f"{relative}: pull_request workflow must not consume repository secrets")
        permissions = _top_level_permissions(source)
        if "pull_request:" in source:
            for name, value in permissions.items():
                if value == "write" and name not in ALLOWED_PR_WRITE_PERMISSIONS:
                    errors.append(
                        f"{relative}: pull_request workflow grants unexpected {name}: write"
                    )
        lines = source.splitlines()
        for index, line in enumerate(lines, start=1):
            match = ACTION_USE_RE.match(line)
            if match is None:
                continue
            value = match.group("value")
            comment = (match.group("comment") or "").strip()
            if value.startswith("./"):
                continue
            if value.startswith("docker://"):
                if "@sha256:" not in value:
                    errors.append(f"{relative}:{index}: docker action is not digest-pinned: {value}")
                continue
            if "@" not in value:
                errors.append(f"{relative}:{index}: malformed action reference: {value}")
                continue
            action, reference = value.rsplit("@", 1)
            if not FULL_SHA_RE.fullmatch(reference):
                errors.append(
                    f"{relative}:{index}: {action} must use an immutable 40-character commit SHA"
                )
            if not comment:
                errors.append(f"{relative}:{index}: pinned action requires a human-readable version comment")
        for index, line in enumerate(lines):
            if "actions/upload-artifact@" not in line:
                continue
            block = "\n".join(lines[index : index + 18])
            if "retention-days:" not in block:
                errors.append(f"{relative}:{index + 1}: artifact upload must set retention-days")
            path_match = re.search(r"(?m)^\s+path:\s*(.+)$", block)
            if path_match:
                artifact_path = path_match.group(1).strip().strip('"\'')
                unsafe = any(
                    fragment in artifact_path.lower()
                    for fragment in (".env", "runtime/", "backups/", "logs/")
                )
                allowed = any(
                    fragment in artifact_path.lower()
                    for fragment in ALLOWED_ARTIFACT_PATH_FRAGMENTS
                )
                if unsafe and not allowed:
                    errors.append(
                        f"{relative}:{index + 1}: artifact path may contain runtime or secret data: {artifact_path}"
                    )
    return errors


def _logical_requirements(source: str) -> tuple[str, ...]:
    entries: list[str] = []
    buffer = ""
    for raw in source.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        continuation = stripped.endswith("\\")
        fragment = stripped[:-1].rstrip() if continuation else stripped
        buffer = f"{buffer} {fragment}".strip()
        if continuation:
            continue
        entries.append(buffer)
        buffer = ""
    if buffer:
        entries.append(buffer)
    return tuple(entries)


def _normalized_package(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).casefold()


def _direct_requirement_names(path: Path) -> set[str]:
    names: set[str] = set()
    for entry in _logical_requirements(path.read_text(encoding="utf-8")):
        if entry.startswith(("-r ", "--requirement ")):
            continue
        match = PACKAGE_RE.match(entry)
        if match:
            names.add(_normalized_package(match.group(1)))
    return names


def _locked_requirement_names(path: Path) -> set[str]:
    names: set[str] = set()
    for entry in _logical_requirements(path.read_text(encoding="utf-8")):
        match = PACKAGE_RE.match(entry)
        if match:
            names.add(_normalized_package(match.group(1)))
    return names


def check_lock_file(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"{_relative(path)}: missing hash-locked dependency graph"]
    entries = _logical_requirements(path.read_text(encoding="utf-8"))
    packages = 0
    for entry in entries:
        if entry.startswith(("--", "-r ", "-c ")):
            continue
        match = PACKAGE_RE.match(entry)
        if match is None:
            continue
        packages += 1
        if HASH_RE.search(entry) is None:
            errors.append(f"{_relative(path)}: {match.group(1)} has no sha256 hash")
    if packages == 0:
        errors.append(f"{_relative(path)}: lock contains no pinned packages")
    return errors


def check_dependency_locks(*, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    runtime_lock = root / "requirements.lock"
    dev_lock = root / "requirements-dev.lock"
    for path in (runtime_lock, dev_lock):
        errors.extend(check_lock_file(path))
    if runtime_lock.exists():
        missing = _direct_requirement_names(root / "requirements.txt") - _locked_requirement_names(runtime_lock)
        for name in sorted(missing):
            errors.append(f"requirements.lock: direct dependency {name} is missing")
    if dev_lock.exists():
        missing = _direct_requirement_names(root / "requirements-dev.txt") - _locked_requirement_names(dev_lock)
        for name in sorted(missing):
            errors.append(f"requirements-dev.lock: direct dependency {name} is missing")
    dockerfile = root / "Dockerfile"
    if dockerfile.exists():
        source = dockerfile.read_text(encoding="utf-8")
        if "COPY requirements.lock" not in source:
            errors.append("Dockerfile: production image must copy requirements.lock")
        if "--require-hashes" not in source or "requirements.lock" not in source:
            errors.append("Dockerfile: production install must use requirements.lock with --require-hashes")
        if "pip install -r requirements.txt" in source:
            errors.append("Dockerfile: mutable requirements.txt install is forbidden")
    for workflow in _workflow_paths(root):
        for index, line in enumerate(workflow.read_text(encoding="utf-8").splitlines(), start=1):
            if not re.search(r"(?:uv\s+pip|python\s+-m\s+pip|\bpip)\s+install", line):
                continue
            if "--upgrade pip" in line:
                errors.append(f"{_relative(workflow, root)}:{index}: CI must not upgrade pip implicitly")
                continue
            if "requirements" in line and (
                ".lock" not in line or "--require-hashes" not in line
            ):
                errors.append(
                    f"{_relative(workflow, root)}:{index}: dependency install must use a hash lock"
                )
    return errors


def check_security_exceptions(*, root: Path = ROOT, today: date | None = None) -> list[str]:
    path = root / ".github" / "security-exceptions.json"
    if not path.exists():
        return [f"{_relative(path, root)}: missing exception registry"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [f"{_relative(path, root)}: invalid JSON: {error}"]
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append(f"{_relative(path, root)}: schema_version must be 1")
    exceptions = payload.get("exceptions")
    if not isinstance(exceptions, list):
        return [*errors, f"{_relative(path, root)}: exceptions must be a list"]
    current = today or date.today()
    required = {"id", "owner", "reason", "expires", "test_reference", "source"}
    seen: set[str] = set()
    for index, item in enumerate(exceptions):
        if not isinstance(item, dict):
            errors.append(f"{_relative(path, root)}: exception #{index + 1} must be an object")
            continue
        missing = required - item.keys()
        if missing:
            errors.append(
                f"{_relative(path, root)}: exception #{index + 1} misses {', '.join(sorted(missing))}"
            )
            continue
        identifier = str(item["id"])
        if identifier in seen:
            errors.append(f"{_relative(path, root)}: duplicate exception id {identifier}")
        seen.add(identifier)
        try:
            expires = date.fromisoformat(str(item["expires"]))
        except ValueError:
            errors.append(f"{_relative(path, root)}: exception {identifier} has invalid expiry")
            continue
        if expires < current:
            errors.append(f"{_relative(path, root)}: exception {identifier} expired on {expires}")
    return errors


def detect_secrets(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return errors
    for line_number, line in enumerate(source.splitlines(), start=1):
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                errors.append(f"{path.as_posix()}:{line_number}: possible {label}")
    return errors


def _is_secret_scan_candidate(path: Path, *, root: Path = ROOT) -> bool:
    relative = _relative(path, root)
    if any(part in SECRET_EXCLUDED_PARTS for part in path.parts):
        return False
    if any(relative.startswith(prefix) for prefix in SECRET_EXCLUDED_PREFIXES):
        return False
    if path.is_dir() or path.stat().st_size > 1_000_000:
        return False
    return True


def check_secrets(paths: Iterable[Path], *, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for path in paths:
        candidate = path if path.is_absolute() else root / path
        if candidate.exists() and _is_secret_scan_candidate(candidate, root=root):
            errors.extend(detect_secrets(candidate))
    return errors


def check_container_files(paths: Iterable[Path], *, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for path in paths:
        candidate = path if path.is_absolute() else root / path
        if not candidate.exists() or candidate.is_dir():
            continue
        relative = _relative(candidate, root)
        lower_name = candidate.name.casefold()
        if "dockerfile" not in lower_name and candidate.suffix not in {".yml", ".yaml"}:
            continue
        source = candidate.read_text(encoding="utf-8")
        patterns = (
            (r"(?im)^\s*ADD\s+https?://", "remote ADD is forbidden"),
            (r"(?im)curl\s+[^\n|]*\|\s*(?:sh|bash)\b", "curl pipe shell is forbidden"),
            (r"(?im)\bchmod\s+777\b", "world-writable chmod is forbidden"),
            (r"(?im)^\s*privileged:\s*true\s*$", "privileged container is forbidden"),
            (r"(?im)^\s*network_mode:\s*host\s*$", "host networking is forbidden"),
            (r"/var/run/docker\.sock", "Docker socket mount is forbidden"),
        )
        for pattern, message in patterns:
            if re.search(pattern, source):
                errors.append(f"{relative}: {message}")
    return errors


def _paths_from_file(path: Path, *, root: Path = ROOT) -> tuple[Path, ...]:
    if not path.exists():
        return ()
    return tuple(
        root / line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _print(errors: Sequence[str]) -> int:
    if not errors:
        print("security gate: OK")
        return 0
    print("security gate failed:", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Velvet security and supply-chain contract")
    parser.add_argument(
        "command",
        choices=("actions", "locks", "exceptions", "secrets", "containers", "all"),
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--paths-from", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    paths = _paths_from_file(args.paths_from, root=root) if args.paths_from else ()
    errors: list[str] = []
    if args.command in {"actions", "all"}:
        errors.extend(check_action_pins(root=root))
    if args.command in {"locks", "all"}:
        errors.extend(check_dependency_locks(root=root))
    if args.command in {"exceptions", "all"}:
        errors.extend(check_security_exceptions(root=root))
    if args.command == "secrets":
        errors.extend(check_secrets(paths, root=root))
    if args.command == "containers":
        errors.extend(check_container_files(paths, root=root))
    return _print(errors)


if __name__ == "__main__":
    raise SystemExit(main())
