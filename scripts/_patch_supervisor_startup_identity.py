from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "velvet_supervisor/runtime.py"


OLD_START = r'''        self._notifier.send(
            "Velvet Supervisor запущен",
            (
                f"PID Supervisor: {os.getpid()}\n"
                f"Проект: {self.settings.project_dir}\n"
                f"API: {self.settings.host}:{self.settings.port}"
            ),
            level="SUCCESS",
        )
'''

NEW_START = r'''        identity = _startup_identity(self.settings.project_dir, self._repository)
        self._notifier.send(
            "Velvet Supervisor запущен",
            (
                f"PID Supervisor: {os.getpid()}\n"
                f"{identity}\n"
                f"API: {self.settings.host}:{self.settings.port}"
            ),
            level="SUCCESS",
        )
'''

HELPER_MARKER = "\ndef _build_child_logger(logs_dir: Path) -> logging.Logger:\n"
HELPER = r'''

def _startup_identity(project_dir: Path, repository: GitRepository) -> str:
    """Render the exact runtime source and Unicode contract used by Supervisor."""
    try:
        git_head = repository.head_sha()[:12]
    except Exception as error:
        git_head = f"unavailable:{type(error).__name__}"
    return (
        f"Проект: {project_dir}\n"
        f"Git HEAD: {git_head}\n"
        f"PYTHONUTF8: {os.environ.get('PYTHONUTF8', 'unset')}\n"
        f"PYTHONIOENCODING: {os.environ.get('PYTHONIOENCODING', 'unset')}"
    )
'''


def main() -> None:
    source = RUNTIME.read_text(encoding="utf-8")
    if source.count(OLD_START) != 1:
        raise RuntimeError("Не найден однозначный startup notification block")
    source = source.replace(OLD_START, NEW_START, 1)
    if source.count(HELPER_MARKER) != 1:
        raise RuntimeError("Не найдена однозначная граница _build_child_logger")
    source = source.replace(HELPER_MARKER, HELPER + HELPER_MARKER, 1)
    ast.parse(source, filename=str(RUNTIME))
    RUNTIME.write_text(source, encoding="utf-8")


if __name__ == "__main__":
    main()
