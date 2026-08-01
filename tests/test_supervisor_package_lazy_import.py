from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_lightweight_supervisor_modules_do_not_import_legacy_config() -> None:
    script = f"""
import sys
sys.path.insert(0, {str(ROOT)!r})
import velvet_supervisor.hermes_incident
import velvet_supervisor.notifier
assert 'velvet_supervisor.config' not in sys.modules
assert 'velvet_supervisor.runtime' not in sys.modules
print('ok')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
