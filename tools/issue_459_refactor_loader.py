from __future__ import annotations

import base64
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
payload = "".join(
    (ROOT / f"tools/issue_459_payload_{index}.txt").read_text(encoding="utf-8").strip()
    for index in range(5)
)
source = zlib.decompress(base64.b85decode(payload.encode("ascii"))).decode("utf-8")
namespace = {"__file__": str(Path(__file__).resolve()), "__name__": "__main__"}
exec(compile(source, "issue_459_refactor.py", "exec"), namespace)
