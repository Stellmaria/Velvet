from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WORKER_VERSION = "1"


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    api_url: str
    token: str
    worker_id: str
    bridge_dir: Path
    poll_seconds: float
    heartbeat_seconds: float
    request_timeout_seconds: float
    job_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "WorkerSettings":
        api_url = os.getenv("VELVET_KRITA_API_URL", "http://127.0.0.1:8766").strip().rstrip("/")
        token = os.getenv("VELVET_KRITA_WORKER_TOKEN", "").strip()
        worker_id = os.getenv("VELVET_KRITA_WORKER_ID", socket.gethostname()).strip()
        bridge = Path(
            os.getenv("VELVET_KRITA_BRIDGE_DIR", str(Path.home() / "VelvetKritaBridge"))
        ).expanduser().resolve()
        if not api_url.startswith(("http://", "https://")):
            raise RuntimeError("VELVET_KRITA_API_URL должен начинаться с http:// или https://.")
        if len(token) < 32:
            raise RuntimeError("VELVET_KRITA_WORKER_TOKEN должен содержать не менее 32 символов.")
        if not worker_id or len(worker_id) > 64:
            raise RuntimeError("VELVET_KRITA_WORKER_ID должен содержать от 1 до 64 символов.")
        return cls(
            api_url=api_url,
            token=token,
            worker_id=worker_id,
            bridge_dir=bridge,
            poll_seconds=max(1.0, float(os.getenv("VELVET_KRITA_POLL_SECONDS", "3"))),
            heartbeat_seconds=max(5.0, float(os.getenv("VELVET_KRITA_HEARTBEAT_SECONDS", "20"))),
            request_timeout_seconds=max(5.0, float(os.getenv("VELVET_KRITA_HTTP_TIMEOUT_SECONDS", "60"))),
            job_timeout_seconds=max(60.0, float(os.getenv("VELVET_KRITA_JOB_TIMEOUT_SECONDS", "1800"))),
        )


class WorkerAPI:
    def __init__(self, settings: WorkerSettings) -> None:
        self.settings = settings

    def heartbeat(self, *, active_job_id: int | None = None, active_revision: int | None = None) -> None:
        self._json(
            "POST",
            "/v1/krita/heartbeat",
            {
                "worker_id": self.settings.worker_id,
                "version": WORKER_VERSION,
                "hostname": platform.node(),
                "active_job_id": active_job_id,
                "active_revision": active_revision,
                "metadata": {"platform": platform.platform(), "python": platform.python_version()},
            },
        )

    def claim(self) -> dict[str, Any] | None:
        response = self._json(
            "POST",
            "/v1/krita/jobs/claim",
            {
                "worker_id": self.settings.worker_id,
                "version": WORKER_VERSION,
                "hostname": platform.node(),
            },
        )
        job = response.get("job")
        return job if isinstance(job, dict) else None

    def download(self, relative_url: str, target: Path, *, lease: str) -> None:
        request = urllib.request.Request(
            self._url(relative_url),
            method="GET",
            headers=self._headers(lease=lease),
        )
        with urllib.request.urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
            temporary = target.with_suffix(target.suffix + ".downloading")
            with temporary.open("wb") as handle:
                shutil.copyfileobj(response, handle)
            os.replace(temporary, target)

    def job_heartbeat(self, job_id: int, revision: int, *, lease: str) -> None:
        self._json(
            "POST",
            f"/v1/krita/jobs/{job_id}/{revision}/heartbeat",
            {},
            lease=lease,
        )

    def upload_result(self, job_id: int, revision: int, output: Path, *, lease: str) -> None:
        body = output.read_bytes()
        request = urllib.request.Request(
            self._url(f"/v1/krita/jobs/{job_id}/{revision}/result"),
            data=body,
            method="PUT",
            headers={
                **self._headers(lease=lease),
                "Content-Type": "image/png",
                "Content-Length": str(len(body)),
            },
        )
        with urllib.request.urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload.get("ok"):
            raise RuntimeError(str(payload.get("error") or "Сервер не принял Krita result."))

    def fail(self, job_id: int, revision: int, *, lease: str, error: str) -> None:
        self._json(
            "POST",
            f"/v1/krita/jobs/{job_id}/{revision}/fail",
            {"error": error[:2000]},
            lease=lease,
        )

    def _json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any],
        *,
        lease: str | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._url(path),
            data=body,
            method=method,
            headers={
                **self._headers(lease=lease),
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Krita API HTTP {error.code}: {detail[:1000]}") from error
        if not isinstance(result, dict) or not result.get("ok"):
            raise RuntimeError(str(result.get("error") if isinstance(result, dict) else result))
        return result

    def _headers(self, *, lease: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.settings.token}",
            "X-Krita-Worker-ID": self.settings.worker_id,
            "User-Agent": f"VelvetKritaWorker/{WORKER_VERSION}",
        }
        if lease:
            headers["X-Krita-Lease"] = lease
        return headers

    def _url(self, path: str) -> str:
        return urllib.parse.urljoin(self.settings.api_url + "/", path.lstrip("/"))


class KritaWorker:
    def __init__(self, settings: WorkerSettings) -> None:
        self.settings = settings
        self.api = WorkerAPI(settings)
        self._prepare_bridge()

    def run(self, *, once: bool = False) -> None:
        print(f"Velvet Krita worker {WORKER_VERSION}: {self.settings.worker_id}")
        print(f"API: {self.settings.api_url}")
        print(f"Bridge: {self.settings.bridge_dir}")
        while True:
            try:
                self.api.heartbeat()
                job = self.api.claim()
                if job is None:
                    if once:
                        return
                    time.sleep(self.settings.poll_seconds)
                    continue
                self._process(job)
            except KeyboardInterrupt:
                return
            except Exception as error:
                print(f"Worker error: {error}")
                if once:
                    raise
                time.sleep(max(3.0, self.settings.poll_seconds))
            if once:
                return

    def _process(self, job: dict[str, Any]) -> None:
        job_id = int(job["job_id"])
        revision = int(job["revision"])
        lease = str(job["lease_token"])
        prefix = f"remote-job-{job_id}-r{revision}"
        source_suffix = Path(str(job.get("source_name") or "source.png")).suffix.lower() or ".png"
        source_path = self.settings.bridge_dir / "sources" / f"{prefix}{source_suffix}"
        output_path = self.settings.bridge_dir / "outputs" / f"{prefix}.png"
        response_path = self.settings.bridge_dir / "responses" / f"{prefix}.json"
        request_path = self.settings.bridge_dir / "requests" / f"{prefix}.json"
        logo_payload = job.get("logo") if isinstance(job.get("logo"), dict) else {"kind": "builtin"}
        local_logo: Path | None = None
        try:
            self.api.download(str(job["source_url"]), source_path, lease=lease)
            if logo_payload.get("kind") != "builtin":
                logo_url = str(logo_payload.get("url") or "")
                if not logo_url:
                    raise RuntimeError("Custom logo job не содержит URL snapshot.")
                logo_suffix = ".svg" if str(logo_payload.get("kind")).casefold() == "svg" else ".png"
                local_logo = self.settings.bridge_dir / "assets" / f"{prefix}-logo{logo_suffix}"
                self.api.download(logo_url, local_logo, lease=lease)
            request = build_local_request(
                job=job,
                bridge_dir=self.settings.bridge_dir,
                source_path=source_path,
                output_path=output_path,
                response_path=response_path,
                local_logo=local_logo,
            )
            temporary = request_path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, request_path)
            print(f"Krita job {job_id}/r{revision}: передан плагину")
            deadline = time.monotonic() + self.settings.job_timeout_seconds
            next_heartbeat = 0.0
            while time.monotonic() < deadline:
                if response_path.is_file():
                    response = json.loads(response_path.read_text(encoding="utf-8"))
                    if response.get("status") != "ok":
                        raise RuntimeError(str(response.get("error") or "Krita plugin вернул ошибку."))
                    if not output_path.is_file():
                        raise RuntimeError("Krita plugin сообщил успех без output PNG.")
                    self.api.upload_result(job_id, revision, output_path, lease=lease)
                    print(f"Krita job {job_id}/r{revision}: результат загружен")
                    return
                now = time.monotonic()
                if now >= next_heartbeat:
                    self.api.heartbeat(active_job_id=job_id, active_revision=revision)
                    self.api.job_heartbeat(job_id, revision, lease=lease)
                    next_heartbeat = now + self.settings.heartbeat_seconds
                time.sleep(1.0)
            raise TimeoutError("Krita plugin не завершил job до таймаута worker-а.")
        except Exception as error:
            try:
                self.api.fail(job_id, revision, lease=lease, error=str(error))
            except Exception as report_error:
                print(f"Не удалось сообщить серверу об ошибке: {report_error}")
            raise
        finally:
            for path in (request_path, request_path.with_suffix(".processing"), response_path, output_path, source_path, local_logo):
                if path is not None:
                    path.unlink(missing_ok=True)

    def _prepare_bridge(self) -> None:
        for name in ("requests", "responses", "outputs", "sources", "previews", "assets"):
            (self.settings.bridge_dir / name).mkdir(parents=True, exist_ok=True)


def build_local_request(
    *,
    job: dict[str, Any],
    bridge_dir: Path,
    source_path: Path,
    output_path: Path,
    response_path: Path,
    local_logo: Path | None,
) -> dict[str, Any]:
    job_id = int(job["job_id"])
    revision = int(job["revision"])
    logo = job.get("logo") if isinstance(job.get("logo"), dict) else {"kind": "builtin"}
    logo_request: dict[str, Any] = {
        "kind": str(logo.get("kind") or "builtin"),
        "name": logo.get("name"),
    }
    if logo_request["kind"] != "builtin":
        if local_logo is None:
            raise ValueError("Custom logo требует локальный snapshot.")
        logo_request.update(
            path=str(local_logo),
            width=float(logo["width"]),
            height=float(logo["height"]),
        )
    return {
        "schema_version": 2,
        "request_id": f"wm-{job_id}-r{revision}",
        "job_id": job_id,
        "revision": revision,
        "bridge_root": str(bridge_dir),
        "logo": logo_request,
        "source_path": str(source_path),
        "output_path": str(output_path),
        "response_path": str(response_path),
        "remove_only": bool(job.get("remove_only", False)),
        "settings": dict(job.get("settings") or {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Velvet remote Windows Krita worker")
    parser.add_argument("--once", action="store_true", help="Обработать не более одной задачи")
    args = parser.parse_args()
    KritaWorker(WorkerSettings.from_env()).run(once=args.once)


if __name__ == "__main__":
    main()
