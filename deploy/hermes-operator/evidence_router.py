#!/usr/bin/env python3
"""Tier-aware coder router with fail-closed PR and GPT Image 2 evidence."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from http import HTTPStatus
from typing import Any

from coder_router import (
    CoderTarget,
    RouterError,
    ThreadingHTTPServer,
    _GITHUB_API,
    _redact_text,
    redact,
)
from codex_image_router import CodexImageRouterHandler, CodexImageRouterSupport
from tier_router import TierAwareCoderRouter

logger = logging.getLogger("velvet.hermes_evidence_router")
_MAX_GITHUB_FILE_PAGES = 30


class EvidenceTierAwareCoderRouter(
    CodexImageRouterSupport,
    TierAwareCoderRouter,
):
    """Preserve typed routing and attach complete file and image evidence."""

    def github_list(
        self,
        target: CoderTarget,
        path: str,
    ) -> list[dict[str, Any]]:
        if not path.startswith("/") or ".." in path or "?" in path:
            raise RouterError(HTTPStatus.BAD_REQUEST, "Некорректный GitHub path.")
        items: list[dict[str, Any]] = []
        for page in range(1, _MAX_GITHUB_FILE_PAGES + 1):
            url = (
                f"{_GITHUB_API}/repos/{target.repository}{path}"
                f"?per_page=100&page={page}"
            )
            request = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {target.github_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "Velvet-Hermes-Coder-Router",
                },
                method="GET",
            )
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=self.timeout_seconds,
                ) as response:
                    raw = response.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as error:
                details = error.read().decode("utf-8", errors="replace")[:2000]
                raise RouterError(
                    HTTPStatus.BAD_GATEWAY,
                    f"GitHub HTTP {error.code}: {_redact_text(details)}",
                ) from error
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                raise RouterError(
                    HTTPStatus.BAD_GATEWAY,
                    f"GitHub недоступен: {type(error).__name__}",
                ) from error
            try:
                result = json.loads(raw)
            except json.JSONDecodeError as error:
                raise RouterError(
                    HTTPStatus.BAD_GATEWAY,
                    "GitHub вернул повреждённый JSON.",
                ) from error
            result = redact(result)
            if not isinstance(result, list) or not all(
                isinstance(item, dict) for item in result
            ):
                raise RouterError(
                    HTTPStatus.BAD_GATEWAY,
                    "GitHub вернул неожиданный список.",
                )
            items.extend(result)
            if len(result) < 100:
                return items
        raise RouterError(
            HTTPStatus.BAD_GATEWAY,
            "GitHub PR превышает поддерживаемый лимит changed-file evidence.",
        )

    def pull_request(self, project: str, number: int) -> dict[str, Any]:
        result = super().pull_request(project, number)
        target = self._target(project)
        files_payload = self.github_list(target, f"/pulls/{number}/files")
        files = sorted(
            str(item["filename"])
            for item in files_payload
            if isinstance(item.get("filename"), str)
        )
        changed_files = result.get("changed_files")
        if type(changed_files) is not int:
            raise RouterError(
                HTTPStatus.BAD_GATEWAY,
                "GitHub changed_files отсутствует в evidence snapshot.",
            )
        if changed_files != len(files):
            raise RouterError(
                HTTPStatus.BAD_GATEWAY,
                "GitHub changed-file count изменился во время evidence snapshot.",
            )
        return {**result, "files": files}


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    host = os.getenv("HERMES_CODER_ROUTER_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.getenv("HERMES_CODER_ROUTER_PORT", "8878"))
    router = EvidenceTierAwareCoderRouter()
    server = ThreadingHTTPServer((host, port), CodexImageRouterHandler)
    server.router = router  # type: ignore[attr-defined]
    logger.info("Hermes evidence-aware tier router listening on %s:%s", host, port)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
