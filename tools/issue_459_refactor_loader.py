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

friendly_path = ROOT / "velvet_bot/domains/media_generation/friendly_worker.py"
friendly = friendly_path.read_text(encoding="utf-8")
friendly = friendly.replace(
    '                "<b>Ауф не смог завершить генерацию</b>\n\n"\n'
    '                f"{escape(message)}\n\n"\n',
    '                "<b>Ауф не смог завершить генерацию</b>\\n\\n"\n'
    '                f"{escape(message)}\\n\\n"\n',
)
friendly_path.write_text(friendly, encoding="utf-8")

test_path = ROOT / "tests/test_media_provider_adapters.py"
test_text = test_path.read_text(encoding="utf-8")
test_text = test_text.replace(
    "KieModelAlias.SEEDREAM_5_PRO",
    "KieModelAlias.WAN_27_IMAGE",
)
test_text = test_text.replace(
    '"seedream/5-pro-text-to-image"',
    '"wan/2-7-image"',
)
test_path.write_text(test_text, encoding="utf-8")
