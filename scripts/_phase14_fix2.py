from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
target = ROOT / "velvet_bot/handlers/analytics_management_aliases.py"
text = target.read_text(encoding="utf-8")
old = '''            f"<b>{escape(name)}</b>?

"
            "Совпадающие старые хэштеги снова станут нераспознанными.",
'''
new = r'''            f"<b>{escape(name)}</b>?\n\n"
            "Совпадающие старые хэштеги снова станут нераспознанными.",
'''
if text.count(old) != 1:
    raise RuntimeError("Expected one broken alias confirmation string")
target.write_text(text.replace(old, new, 1), encoding="utf-8")

(ROOT / "scripts/_phase14_fix2.py").unlink()
(ROOT / ".github/workflows/phase14-fix2.yml").unlink()
