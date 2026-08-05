#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from http import HTTPStatus
from typing import Any

from coder_router import Handler as BaseHandler, RouterError

_IMAGE_RUN = re.compile(r"^[a-f0-9]{32}$")
_MAX_IMAGE_BODY_BYTES = 72 * 1024 * 1024
_MAX_IMAGE_RESULT_BYTES = 50 * 1024 * 1024


class CodexImageRouterSupport:
    """Proxy GPT Image 2 runs to a project-scoped Codex runtime."""

    def submit_image(self, project: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.upstream(self._target(project), "POST", "/v1/images", payload)

    def image_status(self, project: str, run_id: str) -> dict[str, Any]:
        self._validate_image_run_id(run_id)
        return self.upstream(self._target(project), "GET", f"/v1/images/{run_id}")

    def stop_image(self, project: str, run_id: str) -> dict[str, Any]:
        self._validate_image_run_id(run_id)
        return self.upstream(self._target(project), "POST", f"/v1/images/{run_id}/stop", {})

    def image_content(self, project: str, run_id: str) -> tuple[bytes, str, str]:
        self._validate_image_run_id(run_id)
        target = self._target(project)
        request = urllib.request.Request(
            f"{target.base_url}/v1/images/{run_id}/content",
            headers={"Authorization": f"Bearer {target.api_token}", "Accept": "image/*"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=max(120, self.timeout_seconds)) as response:
                payload = response.read(_MAX_IMAGE_RESULT_BYTES + 1)
                mime_type = response.headers.get_content_type()
                disposition = response.headers.get("Content-Disposition", "")
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")[:2000]
            raise RouterError(HTTPStatus.BAD_GATEWAY, f"GPT Image 2 upstream HTTP {error.code}: {details}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise RouterError(HTTPStatus.BAD_GATEWAY, f"GPT Image 2 upstream недоступен: {type(error).__name__}") from error
        if not payload or len(payload) > _MAX_IMAGE_RESULT_BYTES:
            raise RouterError(HTTPStatus.BAD_GATEWAY, "GPT Image 2 upstream вернул пустой или слишком большой файл.")
        match = re.search(r'filename="?([^";]+)', disposition)
        file_name = match.group(1) if match else f"gpt-image-2-{run_id[:8]}.jpg"
        file_name = re.sub(r"[^A-Za-z0-9._-]+", "-", file_name)[:120]
        return payload, mime_type, file_name

    @staticmethod
    def _validate_image_run_id(run_id: str) -> None:
        if not _IMAGE_RUN.fullmatch(run_id):
            raise RouterError(HTTPStatus.BAD_REQUEST, "Некорректный GPT Image 2 run_id.")


class CodexImageRouterHandler(BaseHandler):
    server_version = "HermesCoderImageRouter/1"

    def _image_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise RouterError(HTTPStatus.BAD_REQUEST, "Некорректный Content-Length.") from error
        if not 0 <= length <= _MAX_IMAGE_BODY_BYTES:
            raise RouterError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "GPT Image 2 request слишком большой.")
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as error:
            raise RouterError(HTTPStatus.BAD_REQUEST, "Повреждённый GPT Image 2 JSON.") from error
        if not isinstance(payload, dict):
            raise RouterError(HTTPStatus.BAD_REQUEST, "GPT Image 2 JSON должен быть объектом.")
        return payload

    def _binary(self, payload: bytes, mime_type: str, file_name: str) -> None:
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Content-Disposition", f'attachment; filename="{file_name}"')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        try:
            parts = [part for part in self.path.split("?", 1)[0].split("/") if part]
            if len(parts) in {5, 6} and parts[:2] == ["v1", "coders"] and parts[3] == "images":
                self._auth()
                project, run_id = parts[2], parts[4]
                if len(parts) == 5:
                    self._json(HTTPStatus.OK, self.router.image_status(project, run_id))
                    return
                if parts[5] == "content":
                    self._binary(*self.router.image_content(project, run_id))
                    return
            super().do_GET()
        except RouterError as error:
            self._json(error.status, {"ok": False, "error": str(error)})
        except Exception:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "Внутренняя ошибка GPT Image 2 router."})

    def do_POST(self) -> None:  # noqa: N802
        try:
            parts = [part for part in self.path.split("?", 1)[0].split("/") if part]
            if len(parts) == 4 and parts[:2] == ["v1", "coders"] and parts[3] == "images":
                self._auth()
                self._json(HTTPStatus.ACCEPTED, self.router.submit_image(parts[2], self._image_body()))
                return
            if len(parts) == 6 and parts[:2] == ["v1", "coders"] and parts[3] == "images" and parts[5] == "stop":
                self._auth()
                if self._image_body() != {}:
                    raise RouterError(HTTPStatus.BAD_REQUEST, "stop принимает только пустой JSON.")
                self._json(HTTPStatus.ACCEPTED, self.router.stop_image(parts[2], parts[4]))
                return
            super().do_POST()
        except RouterError as error:
            self._json(error.status, {"ok": False, "error": str(error)})
        except Exception:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "Внутренняя ошибка GPT Image 2 router."})


__all__ = ("CodexImageRouterHandler", "CodexImageRouterSupport")
