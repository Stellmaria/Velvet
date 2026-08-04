from __future__ import annotations

from pathlib import Path


path = Path("scripts/_temporary_refactor_auf_currency.py")
text = path.read_text(encoding="utf-8")
old = '''    if text.count(old) != 1:
        raise RuntimeError(f"Expected one match in {path}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
'''
new = '''    if old not in text:
        raise RuntimeError(f"Expected a match in {path}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
'''
if text.count(old) != 1:
    raise RuntimeError("Could not relax refactor driver replacement contract")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
