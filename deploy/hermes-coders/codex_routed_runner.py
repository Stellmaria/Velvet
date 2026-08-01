#!/usr/bin/env python3
from __future__ import annotations

import os
import re
from typing import Any

from codex_runner import CodexManager, Handler, ThreadingHTTPServer

_MODEL_DIRECTIVE = re.compile(
    r"(?i)(?:^|\s)(?:/model|model|модель)\s*[:=]?\s*"
    r"(luna|terra|sol|луна|терра|сол)\b"
)
_HIGH_COMPLEXITY = re.compile(
    r"(?i)(архитектур|рефактор|миграц|безопасност|security|race.?condition|"
    r"полный анализ|несколько сервис|cross.?service|distributed|сложн)"
)
_LOW_COMPLEXITY = re.compile(
    r"(?i)(опечатк|readme|документац|переимен|форматир|маленьк|прост|"
    r"один тест|single test|typo|docs?\b)"
)
_ALIASES = {
    "luna": "gpt-5.6-luna",
    "луна": "gpt-5.6-luna",
    "terra": "gpt-5.6-terra",
    "терра": "gpt-5.6-terra",
    "sol": "gpt-5.6-sol",
    "сол": "gpt-5.6-sol",
}


def select_model(prompt: str, *, default: str, allowed: tuple[str, ...]) -> str:
    directive = _MODEL_DIRECTIVE.search(prompt)
    if directive:
        selected = _ALIASES[directive.group(1).casefold()]
        if selected in allowed:
            return selected
    if len(prompt) >= 8_000 or _HIGH_COMPLEXITY.search(prompt):
        if "gpt-5.6-sol" in allowed:
            return "gpt-5.6-sol"
    if len(prompt) <= 6_000 and _LOW_COMPLEXITY.search(prompt):
        if "gpt-5.6-luna" in allowed:
            return "gpt-5.6-luna"
    return default


class RoutedCodexManager(CodexManager):
    def capabilities(self) -> dict[str, Any]:
        payload = super().capabilities()
        return {
            **payload,
            "routing": {
                "default": self.default_model,
                "small": "gpt-5.6-luna",
                "complex": "gpt-5.6-sol",
                "explicit": ["luna", "terra", "sol"],
            },
        }

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        routed = dict(payload)
        if "model" not in routed:
            prompt = routed.get("input")
            if isinstance(prompt, str):
                routed["model"] = select_model(
                    prompt,
                    default=self.default_model,
                    allowed=self.allowed_models,
                )
        return super().submit(routed)


def main() -> int:
    host = os.environ.get("CODEX_RUNNER_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.environ.get("CODEX_RUNNER_PORT", "8642"))
    if not 1024 <= port <= 65535:
        raise RuntimeError("CODEX_RUNNER_PORT должен быть от 1024 до 65535")
    manager = RoutedCodexManager()
    server = ThreadingHTTPServer((host, port), Handler)
    server.manager = manager  # type: ignore[attr-defined]
    print(
        f"Velvet routed Codex runner listening on {host}:{port}; "
        f"default={manager.default_model}; models={','.join(manager.allowed_models)}",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
