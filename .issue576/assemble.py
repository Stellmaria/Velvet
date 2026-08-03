from __future__ import annotations

import base64
import hashlib
import io
import shutil
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_DIR = ROOT / ".issue576"
EXPECTED_SHA256 = "ca866f59988c82037a56f68a7c5b52a4d53e3ee6b32928d2d27493691a351a08"
ALLOWED = {
    "deploy/hermes-coders/codex_provider_chain_runner.py",
    "deploy/hermes-operator/coder_router.py",
    "deploy/hermes-operator/coderctl.py",
    "tests/test_hermes_codex_provider_chain.py",
    "tests/test_hermes_coder_orchestration.py",
    "tests/test_hermes_router_recovery.py",
    "docs/worklog/2026-08-03-tier-aware-hermes-model-routing.md",
}


def main() -> int:
    parts = sorted(BUNDLE_DIR.glob("bundle.part*"))
    if [path.name for path in parts] != [
        "bundle.part01",
        "bundle.part02",
        "bundle.part03",
        "bundle.part04",
    ]:
        raise SystemExit("Issue 576 bundle is incomplete")

    encoded = "".join(path.read_text(encoding="ascii").strip() for path in parts)
    archive = base64.b64decode(encoded, validate=True)
    actual = hashlib.sha256(archive).hexdigest()
    if actual != EXPECTED_SHA256:
        raise SystemExit(
            f"Issue 576 bundle checksum mismatch: expected={EXPECTED_SHA256} actual={actual}"
        )

    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        members = bundle.getmembers()
        file_names = {member.name for member in members if member.isfile()}
        if file_names != ALLOWED:
            raise SystemExit(
                "Issue 576 bundle file set mismatch: "
                + ", ".join(sorted(file_names ^ ALLOWED))
            )
        if any(not member.isfile() for member in members):
            raise SystemExit("Issue 576 bundle contains a non-file member")

        root = ROOT.resolve()
        for member in members:
            target = (ROOT / member.name).resolve()
            if root not in target.parents:
                raise SystemExit(f"Unsafe bundle path: {member.name}")
            source = bundle.extractfile(member)
            if source is None:
                raise SystemExit(f"Cannot read bundle member: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read())

    shutil.rmtree(BUNDLE_DIR)
    print("Issue 576 reviewed source bundle reconstructed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
