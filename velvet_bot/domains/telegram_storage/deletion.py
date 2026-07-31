from __future__ import annotations

import logging
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Iterable, Iterator, Literal

logger = logging.getLogger(__name__)

DeletionKind = Literal["file", "symlink", "directory"]
DeletionIssueCode = Literal[
    "invalid_path",
    "outside_allowlist",
    "allowlist_root",
    "protected_path",
    "protected_tree",
    "blocked_name",
    "symlink_parent",
    "invalid_parent",
    "recursive_not_allowed",
    "unsupported_type",
    "inspection_failed",
    "changed_since_plan",
    "delete_failed",
]


@dataclass(frozen=True, slots=True)
class DeletionIssue:
    path: Path
    code: DeletionIssueCode
    message: str
    stage: Literal["plan", "delete"] = "plan"


@dataclass(frozen=True, slots=True)
class DeletionPlanItem:
    path: Path
    root: Path
    kind: DeletionKind
    size_bytes: int
    fingerprint: tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class DeletionResult:
    policy_name: str
    planned: tuple[DeletionPlanItem, ...]
    deleted_paths: tuple[Path, ...]
    issues: tuple[DeletionIssue, ...]
    freed_bytes: int
    dry_run: bool

    @property
    def deleted_count(self) -> int:
        return len(self.deleted_paths)

    @property
    def complete(self) -> bool:
        return not self.issues and (
            self.dry_run or len(self.deleted_paths) == len(self.planned)
        )

    def __iter__(self) -> Iterator[int]:
        # Compatibility with the previous ``deleted, freed = remove_paths(...)`` API.
        yield self.deleted_count
        yield self.freed_bytes


@dataclass(frozen=True, slots=True)
class DeletionPolicy:
    name: str
    allowed_roots: tuple[Path, ...]
    protected_exact: tuple[Path, ...] = ()
    protected_trees: tuple[Path, ...] = ()
    allow_recursive_directories: bool = False

    def __post_init__(self) -> None:
        roots = _normalize_policy_paths(self.allowed_roots)
        protected_exact = _normalize_policy_paths(self.protected_exact)
        protected_trees = _normalize_policy_paths(self.protected_trees)
        if not roots:
            raise ValueError(f"DeletionPolicy {self.name!r} has an empty allowlist.")
        for root in roots:
            if root == Path(root.anchor):
                raise ValueError("Filesystem root cannot be a deletion allowlist root.")
            if root in protected_exact:
                raise ValueError(f"Protected path cannot be an allowlist root: {root}")
            if any(_is_within(root, tree) for tree in protected_trees):
                raise ValueError(f"Protected tree cannot be an allowlist root: {root}")
            issue = _existing_chain_issue(root)
            if issue is not None:
                raise ValueError(
                    f"Deletion allowlist root is unsafe: {issue.path} "
                    f"({issue.code})."
                )
            try:
                value = root.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISDIR(value.st_mode):
                raise ValueError(
                    f"Deletion allowlist root must be a real directory: {root}"
                )
        object.__setattr__(self, "allowed_roots", roots)
        object.__setattr__(self, "protected_exact", protected_exact)
        object.__setattr__(self, "protected_trees", protected_trees)

    def plan(self, paths: Iterable[str | os.PathLike[str]]) -> DeletionResult:
        return delete_paths(paths, policy=self, dry_run=True)


def build_storage_deletion_policy(
    *,
    name: str,
    roots: Iterable[Path],
    project_dir: Path,
    data_dir: Path | None = None,
    allow_recursive_directories: bool = False,
) -> DeletionPolicy:
    project = _canonical_config_path(project_dir)
    home = _canonical_config_path(Path.home())
    filesystem_root = Path(project.anchor)
    protected_exact = [filesystem_root, home, project]
    protected_trees = [project / ".git"]
    if data_dir is not None:
        data = _canonical_config_path(data_dir)
        protected_exact.append(data)
        protected_trees.extend(
            (
                data / "postgres",
                data / "postgresql",
                data / "pgdata",
            )
        )
    return DeletionPolicy(
        name=name,
        allowed_roots=tuple(roots),
        protected_exact=tuple(protected_exact),
        protected_trees=tuple(protected_trees),
        allow_recursive_directories=allow_recursive_directories,
    )


def temporary_deletion_policy() -> DeletionPolicy:
    project = _configured_path(
        os.getenv("SUPERVISOR_PROJECT_DIR", ""),
        default=Path.cwd(),
        base=Path.cwd(),
    )
    staging = _configured_path(
        os.getenv("STORAGE_STAGING_DIR", ""),
        default=project / "runtime" / "telegram-storage",
        base=project,
    )
    bridge = _configured_path(
        os.getenv("KRITA_BRIDGE_DIR", ""),
        default=Path.home() / "VelvetKritaBridge",
        base=project,
    )
    data_raw = os.getenv("VELVET_DATA_DIR", "").strip()
    data_dir = (
        _configured_path(data_raw, default=project / "data", base=project)
        if data_raw
        else None
    )
    return build_storage_deletion_policy(
        name="telegram-storage-temporary",
        roots=(staging, bridge),
        project_dir=project,
        data_dir=data_dir,
        allow_recursive_directories=True,
    )


def delete_paths(
    paths: Iterable[str | os.PathLike[str]],
    *,
    policy: DeletionPolicy,
    dry_run: bool = False,
) -> DeletionResult:
    planned: list[DeletionPlanItem] = []
    deleted: list[Path] = []
    issues: list[DeletionIssue] = []
    normalized: set[Path] = set()

    for raw_path in paths:
        try:
            path = _lexical_absolute(raw_path)
        except (TypeError, ValueError, OSError) as error:
            issue_path = Path(os.fspath(raw_path) or ".")
            issues.append(
                DeletionIssue(
                    path=issue_path,
                    code="invalid_path",
                    message=str(error),
                )
            )
            continue
        normalized.add(path)

    for path in sorted(normalized, key=lambda value: len(value.parts), reverse=True):
        item, issue = _plan_one(path, policy)
        if issue is not None:
            issues.append(issue)
        elif item is not None:
            planned.append(item)

    # A policy refusal makes the whole batch fail closed. Runtime filesystem
    # failures can still produce a partial result and are reported explicitly.
    if not dry_run and not issues:
        for item in planned:
            current, issue = _plan_one(item.path, policy)
            if issue is not None:
                issues.append(_delete_stage(issue))
                continue
            if current is None:
                issues.append(
                    DeletionIssue(
                        path=item.path,
                        code="changed_since_plan",
                        message="Path disappeared after deletion planning.",
                        stage="delete",
                    )
                )
                continue
            if (
                current.kind != item.kind
                or current.root != item.root
                or current.fingerprint != item.fingerprint
                or current.size_bytes != item.size_bytes
            ):
                issues.append(
                    DeletionIssue(
                        path=item.path,
                        code="changed_since_plan",
                        message="Path changed after deletion planning.",
                        stage="delete",
                    )
                )
                continue
            try:
                if item.kind in {"file", "symlink"}:
                    item.path.unlink()
                else:
                    _delete_directory(
                        item.path,
                        policy,
                        item.root,
                        item.fingerprint,
                    )
            except OSError as error:
                issues.append(
                    DeletionIssue(
                        path=item.path,
                        code="delete_failed",
                        message=f"{type(error).__name__}: {error}",
                        stage="delete",
                    )
                )
                continue
            deleted.append(item.path)

    deleted_set = set(deleted)
    result = DeletionResult(
        policy_name=policy.name,
        planned=tuple(planned),
        deleted_paths=tuple(deleted),
        issues=tuple(issues),
        freed_bytes=sum(
            item.size_bytes for item in planned if item.path in deleted_set
        ),
        dry_run=dry_run,
    )
    _audit_result(result)
    return result


def _plan_one(
    path: Path,
    policy: DeletionPolicy,
) -> tuple[DeletionPlanItem | None, DeletionIssue | None]:
    root, issue = _validate_common(path, policy)
    if issue is not None:
        return None, issue
    assert root is not None
    try:
        value = path.lstat()
    except FileNotFoundError:
        return None, None
    except OSError as error:
        return None, DeletionIssue(
            path=path,
            code="inspection_failed",
            message=f"{type(error).__name__}: {error}",
        )

    mode = value.st_mode
    if stat.S_ISLNK(mode):
        kind: DeletionKind = "symlink"
        size = int(value.st_size)
    elif stat.S_ISREG(mode):
        kind = "file"
        size = int(value.st_size)
    elif stat.S_ISDIR(mode):
        if not policy.allow_recursive_directories:
            return None, DeletionIssue(
                path=path,
                code="recursive_not_allowed",
                message="Recursive directory deletion is disabled by policy.",
            )
        kind = "directory"
        try:
            size = _validate_directory_tree(path, policy, root)
        except _DeletionValidationError as error:
            return None, error.issue
        except OSError as error:
            return None, DeletionIssue(
                path=path,
                code="inspection_failed",
                message=f"{type(error).__name__}: {error}",
            )
    else:
        return None, DeletionIssue(
            path=path,
            code="unsupported_type",
            message=(
                "Only regular files, symlinks and explicitly allowed "
                "directories may be deleted."
            ),
        )
    return (
        DeletionPlanItem(
            path=path,
            root=root,
            kind=kind,
            size_bytes=size,
            fingerprint=_fingerprint(value),
        ),
        None,
    )


def _validate_common(
    path: Path,
    policy: DeletionPolicy,
) -> tuple[Path | None, DeletionIssue | None]:
    matching = tuple(root for root in policy.allowed_roots if _is_within(path, root))
    if not matching:
        return None, DeletionIssue(
            path=path,
            code="outside_allowlist",
            message="Path is outside configured deletion roots.",
        )
    root = max(matching, key=lambda value: len(value.parts))
    root_issue = _existing_chain_issue(root)
    if root_issue is not None:
        return None, root_issue
    if path == root:
        return None, DeletionIssue(
            path=path,
            code="allowlist_root",
            message="Deletion of an allowlist root is forbidden.",
        )
    if path == Path(path.anchor) or path in policy.protected_exact:
        return None, DeletionIssue(
            path=path,
            code="protected_path",
            message=(
                "Protected filesystem, home, application or data path "
                "cannot be deleted."
            ),
        )
    if any(_is_within(path, protected) for protected in policy.protected_trees):
        return None, DeletionIssue(
            path=path,
            code="protected_tree",
            message="Path belongs to a protected checkout or database tree.",
        )
    folded_parts = tuple(part.casefold() for part in path.parts)
    if ".git" in folded_parts or path.name.casefold().startswith(".env"):
        return None, DeletionIssue(
            path=path,
            code="blocked_name",
            message="Git metadata and environment files cannot be deleted.",
        )

    current = root
    try:
        relative = path.relative_to(root)
    except ValueError:
        return None, DeletionIssue(
            path=path,
            code="outside_allowlist",
            message="Path is outside configured deletion roots.",
        )
    for part in relative.parts[:-1]:
        current = current / part
        try:
            value = current.lstat()
        except FileNotFoundError:
            break
        except OSError as error:
            return None, DeletionIssue(
                path=current,
                code="inspection_failed",
                message=f"{type(error).__name__}: {error}",
            )
        if stat.S_ISLNK(value.st_mode):
            return None, DeletionIssue(
                path=current,
                code="symlink_parent",
                message=(
                    "A parent directory is a symlink; target confinement "
                    "is not provable."
                ),
            )
        if not stat.S_ISDIR(value.st_mode):
            return None, DeletionIssue(
                path=current,
                code="invalid_parent",
                message="A parent path component is not a directory.",
            )
    return root, None


def _existing_chain_issue(path: Path) -> DeletionIssue | None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            value = current.lstat()
        except FileNotFoundError:
            return None
        except OSError as error:
            return DeletionIssue(
                path=current,
                code="inspection_failed",
                message=f"{type(error).__name__}: {error}",
            )
        if stat.S_ISLNK(value.st_mode):
            return DeletionIssue(
                path=current,
                code="symlink_parent",
                message=(
                    "Deletion allowlist roots and their parents must not "
                    "be symlinks."
                ),
            )
        if current != path and not stat.S_ISDIR(value.st_mode):
            return DeletionIssue(
                path=current,
                code="invalid_parent",
                message="A deletion root parent is not a directory.",
            )
    return None


def _validate_directory_tree(path: Path, policy: DeletionPolicy, root: Path) -> int:
    total = 0
    with os.scandir(path) as entries:
        for entry in entries:
            child = _lexical_absolute(entry.path)
            child_root, issue = _validate_common(child, policy)
            if issue is not None or child_root != root:
                raise _DeletionValidationError(
                    issue
                    or DeletionIssue(
                        path=child,
                        code="outside_allowlist",
                        message=(
                            "Directory child escaped its configured "
                            "deletion root."
                        ),
                    )
                )
            value = child.lstat()
            if stat.S_ISLNK(value.st_mode) or stat.S_ISREG(value.st_mode):
                total += int(value.st_size)
            elif stat.S_ISDIR(value.st_mode):
                total += _validate_directory_tree(child, policy, root)
            else:
                raise _DeletionValidationError(
                    DeletionIssue(
                        path=child,
                        code="unsupported_type",
                        message=(
                            "Directory contains an unsupported filesystem "
                            "object."
                        ),
                    )
                )
    return total


def _delete_directory(
    path: Path,
    policy: DeletionPolicy,
    root: Path,
    expected_fingerprint: tuple[int, int, int],
) -> None:
    current_root, issue = _validate_common(path, policy)
    if issue is not None or current_root != root:
        raise OSError("Directory failed policy revalidation before deletion.")
    value = path.lstat()
    if (
        not stat.S_ISDIR(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or _fingerprint(value) != expected_fingerprint
    ):
        raise OSError("Directory changed identity or type before deletion.")
    with os.scandir(path) as entries:
        children = [Path(entry.path) for entry in entries]
    for child in children:
        child = _lexical_absolute(child)
        child_root, child_issue = _validate_common(child, policy)
        if child_issue is not None or child_root != root:
            raise OSError("Directory child failed policy revalidation.")
        child_value = child.lstat()
        if stat.S_ISLNK(child_value.st_mode) or stat.S_ISREG(child_value.st_mode):
            child.unlink()
        elif stat.S_ISDIR(child_value.st_mode):
            _delete_directory(
                child,
                policy,
                root,
                _fingerprint(child_value),
            )
        else:
            raise OSError("Directory contains an unsupported filesystem object.")
    final_value = path.lstat()
    if _fingerprint(final_value) != expected_fingerprint:
        raise OSError("Directory changed identity before final removal.")
    path.rmdir()


def _normalize_policy_paths(paths: Iterable[Path]) -> tuple[Path, ...]:
    result: list[Path] = []
    seen: set[Path] = set()
    for value in paths:
        path = _canonical_config_path(value)
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return tuple(result)


def _canonical_config_path(path: str | os.PathLike[str]) -> Path:
    raw = os.fspath(path)
    if not raw or "\x00" in raw:
        raise ValueError("Deletion policy path is empty or contains NUL.")
    expanded = os.path.expanduser(raw)
    candidate = Path(expanded)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return _lexical_absolute(candidate)


def _configured_path(
    raw: str,
    *,
    default: Path,
    base: Path,
) -> Path:
    value = Path(raw).expanduser() if raw.strip() else default
    if not value.is_absolute():
        value = base / value
    return _canonical_config_path(value)


def _lexical_absolute(path: str | os.PathLike[str]) -> Path:
    raw = os.fspath(path)
    if not raw or "\x00" in raw:
        raise ValueError("Deletion path is empty or contains NUL.")
    if os.name != "nt":
        windows = PureWindowsPath(raw)
        if windows.drive or raw.startswith(("\\\\", "//")):
            raise ValueError("Foreign Windows drive and UNC paths are forbidden.")
    expanded = os.path.expanduser(raw)
    candidate = Path(expanded)
    if not candidate.is_absolute():
        raise ValueError("Deletion path must be absolute.")
    return Path(os.path.abspath(os.path.normpath(expanded)))


def _fingerprint(value: os.stat_result) -> tuple[int, int, int]:
    return int(value.st_dev), int(value.st_ino), int(value.st_mode)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _delete_stage(issue: DeletionIssue) -> DeletionIssue:
    return DeletionIssue(
        path=issue.path,
        code=issue.code,
        message=issue.message,
        stage="delete",
    )


def _audit_result(result: DeletionResult) -> None:
    for issue in result.issues:
        logger.warning(
            "telegram_storage_deletion_issue "
            "policy=%s stage=%s code=%s path=%s",
            result.policy_name,
            issue.stage,
            issue.code,
            issue.path,
        )
    logger.info(
        "telegram_storage_deletion_result "
        "policy=%s dry_run=%s planned=%s deleted=%s issues=%s freed_bytes=%s",
        result.policy_name,
        result.dry_run,
        len(result.planned),
        result.deleted_count,
        len(result.issues),
        result.freed_bytes,
    )


class _DeletionValidationError(RuntimeError):
    def __init__(self, issue: DeletionIssue) -> None:
        super().__init__(issue.message)
        self.issue = issue


__all__ = (
    "DeletionIssue",
    "DeletionPlanItem",
    "DeletionPolicy",
    "DeletionResult",
    "build_storage_deletion_policy",
    "delete_paths",
    "temporary_deletion_policy",
)
