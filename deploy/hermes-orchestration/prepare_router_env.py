from __future__ import annotations

import os
import sys
from pathlib import Path


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 3:
        raise SystemExit("usage: prepare_router_env.py VELVET_ENV MAX_ENV ROUTER_ENV")
    velvet_path, max_path, router_path = map(Path, args)
    for path in (velvet_path, max_path, router_path):
        if not path.is_file():
            raise SystemExit(f"missing required env file: {path}")
    velvet = parse_env(velvet_path)
    maximum = parse_env(max_path)
    router = parse_env(router_path)
    velvet_token = velvet.get("GH_TOKEN", "")
    max_token = maximum.get("GH_TOKEN", "")
    if len(velvet_token) < 24 or len(max_token) < 24:
        raise SystemExit("coder GH_TOKEN is missing or too short")
    if velvet_token == max_token:
        raise SystemExit("Velvet and Max coder GH_TOKEN values must be distinct")
    router.update(
        {
            "HERMES_CODER_VELVET_GITHUB_TOKEN": velvet_token,
            "HERMES_CODER_MAX_GITHUB_TOKEN": max_token,
        }
    )
    required = (
        "HERMES_CODER_ROUTER_CLIENT_TOKEN",
        "HERMES_CODER_VELVET_TOKEN",
        "HERMES_CODER_MAX_TOKEN",
        "HERMES_CODER_VELVET_BASE_URL",
        "HERMES_CODER_MAX_BASE_URL",
    )
    missing = [name for name in required if len(router.get(name, "")) < 8]
    if missing:
        raise SystemExit("router env is incomplete: " + ", ".join(missing))
    router_path.write_text(
        "\n".join(f"{name}={value}" for name, value in sorted(router.items())) + "\n",
        encoding="utf-8",
    )
    os.chmod(router_path, 0o600)
    print("Router GitHub verification credentials prepared without printing values.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
