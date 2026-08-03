from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = ROOT / "tests"
DURATION_HINTS_FILE = ROOT / "scripts" / "ci_test_durations.json"
FALLBACK_SECONDS_PER_BYTE = 1.0 / 100_000
MIN_FALLBACK_SECONDS = 0.02
PREFLIGHT_TESTS = frozenset(
    {
        Path("tests/test_package_architecture_inventory.py"),
        Path("tests/test_telegram_navigation_inventory.py"),
    }
)


def discover_test_files() -> tuple[Path, ...]:
    """Return tests handled by the parallel jobs.

    The small architecture/navigation contracts run in the preflight job so a
    stale generated inventory fails before the dependency-heavy jobs finish.
    """

    return tuple(
        sorted(
            path.relative_to(ROOT)
            for path in TESTS_ROOT.rglob("test_*.py")
            if path.is_file() and path.relative_to(ROOT) not in PREFLIGHT_TESTS
        )
    )


def load_duration_hints(
    path: Path = DURATION_HINTS_FILE,
) -> dict[Path, float]:
    """Load measured per-file runtime estimates used to balance CI shards."""

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("duration hints must be a JSON object")

    hints: dict[Path, float] = {}
    for raw_name, raw_seconds in sorted(raw.items()):
        if not isinstance(raw_name, str):
            raise ValueError("duration hint paths must be strings")
        test_path = Path(raw_name)
        if (
            test_path.is_absolute()
            or ".." in test_path.parts
            or test_path.parent != Path("tests")
            or not test_path.name.startswith("test_")
            or test_path.suffix != ".py"
        ):
            raise ValueError(f"invalid duration hint path: {raw_name!r}")
        if (
            isinstance(raw_seconds, bool)
            or not isinstance(raw_seconds, (int, float))
            or raw_seconds <= 0
        ):
            raise ValueError(
                f"duration hint for {raw_name!r} must be a positive number"
            )
        hints[test_path] = float(raw_seconds)
    return hints


def estimate_test_duration(
    path: Path,
    *,
    duration_hints: Mapping[Path, float],
) -> float:
    """Return measured runtime, falling back to a small source-size estimate."""

    hinted = duration_hints.get(path)
    if hinted is not None:
        return hinted
    source_bytes = max((ROOT / path).stat().st_size, 1)
    return max(source_bytes * FALLBACK_SECONDS_PER_BYTE, MIN_FALLBACK_SECONDS)


def partition_test_files(
    files: Sequence[Path],
    *,
    total: int,
    duration_hints: Mapping[Path, float] | None = None,
) -> tuple[tuple[Path, ...], ...]:
    """Balance files across shards using measured runtime where available."""

    if total < 1:
        raise ValueError("total must be at least 1")

    hints = load_duration_hints() if duration_hints is None else duration_hints
    buckets: list[list[Path]] = [[] for _ in range(total)]
    loads = [0.0 for _ in range(total)]
    weighted = sorted(
        files,
        key=lambda path: (
            -estimate_test_duration(path, duration_hints=hints),
            path.as_posix(),
        ),
    )

    for path in weighted:
        shard = min(range(total), key=lambda index: (loads[index], index))
        buckets[shard].append(path)
        loads[shard] += estimate_test_duration(path, duration_hints=hints)

    return tuple(tuple(sorted(bucket)) for bucket in buckets)


def partition_estimated_loads(
    partitions: Sequence[Sequence[Path]],
    *,
    duration_hints: Mapping[Path, float],
) -> tuple[float, ...]:
    return tuple(
        sum(
            estimate_test_duration(path, duration_hints=duration_hints)
            for path in partition
        )
        for partition in partitions
    )


def verify_partitions(*, total: int) -> int:
    files = discover_test_files()
    hints = load_duration_hints()
    stale_hints = sorted(set(hints) - set(files))
    partitions = partition_test_files(files, total=total, duration_hints=hints)
    assigned = [path for partition in partitions for path in partition]
    counts = Counter(assigned)

    duplicates = sorted(path for path, count in counts.items() if count != 1)
    missing = sorted(set(files) - set(assigned))
    empty = [index for index, partition in enumerate(partitions) if not partition]

    if stale_hints or duplicates or missing or empty:
        print(f"stale duration hints: {[path.as_posix() for path in stale_hints]}")
        print(f"duplicate assignments: {[path.as_posix() for path in duplicates]}")
        print(f"missing assignments: {[path.as_posix() for path in missing]}")
        print(f"empty shards: {empty}")
        return 1

    loads = partition_estimated_loads(partitions, duration_hints=hints)
    for index, (partition, estimated_seconds) in enumerate(
        zip(partitions, loads, strict=True)
    ):
        byte_count = sum((ROOT / path).stat().st_size for path in partition)
        print(
            f"shard {index}: {len(partition)} files, "
            f"{byte_count} source bytes, "
            f"{estimated_seconds:.2f}s estimated"
        )
    print(
        f"verified {len(files)} parallel test files across {total} shards "
        f"using {len(hints)} measured duration hints"
    )
    return 0


def run_shard(
    *,
    index: int,
    total: int,
    failfast: bool,
    durations: int,
    list_only: bool,
) -> int:
    if not 0 <= index < total:
        raise ValueError(f"index must be between 0 and {total - 1}")

    partitions = partition_test_files(discover_test_files(), total=total)
    selected = partitions[index]
    if not selected:
        print(f"shard {index} has no tests", file=sys.stderr)
        return 2

    print(f"shard {index}/{total - 1}: {len(selected)} test files", flush=True)
    for path in selected:
        print(path.as_posix(), flush=True)

    if list_only:
        return 0

    command = [sys.executable, "-m", "unittest", "-v"]
    if failfast:
        command.append("-f")
    if durations >= 0:
        command.extend(["--durations", str(durations)])
    command.extend(path.as_posix() for path in selected)

    return subprocess.run(command, cwd=ROOT, check=False).returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a deterministic, runtime-balanced unittest shard."
    )
    parser.add_argument("--index", type=int)
    parser.add_argument("--total", type=int, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--list", action="store_true", dest="list_only")
    parser.add_argument("--failfast", action="store_true")
    parser.add_argument("--durations", type=int, default=30)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.verify:
        return verify_partitions(total=args.total)
    if args.index is None:
        parser.error("--index is required unless --verify is used")

    return run_shard(
        index=args.index,
        total=args.total,
        failfast=args.failfast,
        durations=args.durations,
        list_only=args.list_only,
    )


if __name__ == "__main__":
    raise SystemExit(main())
