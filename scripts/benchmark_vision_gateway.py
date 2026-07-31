from __future__ import annotations

import argparse
import base64
import json
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Sample:
    index: int
    latency_seconds: float
    response_chars: int
    docker_memory: str | None = None
    docker_cpu: str | None = None


def _request_json(url: str, payload: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "X-Request-ID": "vision-benchmark"},
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {detail[:1000]}") from error
    result = json.loads(body)
    if not isinstance(result, dict):
        raise RuntimeError("Gateway returned a non-object JSON response.")
    return result


def _docker_stats(container: str) -> tuple[str | None, str | None]:
    if not container:
        return None, None
    result = subprocess.run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            container,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None, None
    payload = json.loads(result.stdout.splitlines()[0])
    return str(payload.get("MemUsage") or "") or None, str(payload.get("CPUPerc") or "") or None


def _sample_stats_while_running(
    container: str,
    stop: threading.Event,
    samples: list[tuple[str | None, str | None]],
) -> None:
    while not stop.wait(0.5):
        try:
            samples.append(_docker_stats(container))
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            continue


def _extract_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Gateway response has no choices.")
    first = choices[0]
    if not isinstance(first, dict):
        raise RuntimeError("Gateway choice is invalid.")
    message = first.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("Gateway choice has no message.")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Gateway returned an empty response.")
    return content


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    endpoint = args.endpoint.rstrip("/")
    health = _request_json(f"{endpoint}/health", None, args.timeout)
    model = str(health.get("model") or args.model).strip()
    if not model:
        raise RuntimeError("Model is missing from health response and arguments.")

    image_bytes = Path(args.image).read_bytes()
    if len(image_bytes) > args.max_input_bytes:
        raise RuntimeError("Input image exceeds --max-input-bytes.")
    suffix = Path(args.image).suffix.casefold()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix)
    if mime is None:
        raise RuntimeError("Benchmark image must be JPEG, PNG or WebP.")
    data_uri = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    payload = {
        "model": model,
        "stream": False,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Return concise JSON with keys subjects, composition, "
                            "lighting, palette, confidence. Describe only visible facts."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ],
    }

    samples: list[Sample] = []
    for index in range(args.rounds):
        stats: list[tuple[str | None, str | None]] = []
        stop = threading.Event()
        monitor = None
        if args.docker_container:
            monitor = threading.Thread(
                target=_sample_stats_while_running,
                args=(args.docker_container, stop, stats),
                daemon=True,
            )
            monitor.start()
        started = time.monotonic()
        response = _request_json(
            f"{endpoint}/v1/chat/completions",
            payload,
            args.timeout,
        )
        latency = time.monotonic() - started
        stop.set()
        if monitor is not None:
            monitor.join(timeout=2)
        content = _extract_content(response)
        memory, cpu = stats[-1] if stats else _docker_stats(args.docker_container)
        samples.append(
            Sample(
                index=index + 1,
                latency_seconds=round(latency, 3),
                response_chars=len(content),
                docker_memory=memory,
                docker_cpu=cpu,
            )
        )

    warm = [sample.latency_seconds for sample in samples[1:]] or [samples[0].latency_seconds]
    result = {
        "endpoint": endpoint,
        "model": model,
        "digest": health.get("digest"),
        "rounds": args.rounds,
        "cold_latency_seconds": samples[0].latency_seconds,
        "warm_median_seconds": round(statistics.median(warm), 3),
        "warm_max_seconds": round(max(warm), 3),
        "samples": [asdict(sample) for sample in samples],
    }
    if args.output:
        Path(args.output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark Velvet local VL gateway.")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8080")
    parser.add_argument("--image", required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--max-input-bytes", type=int, default=25 * 1024 * 1024)
    parser.add_argument("--docker-container", default="velvet-vision-runtime-1")
    parser.add_argument("--output", default="")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.rounds < 1 or args.rounds > 20:
        raise SystemExit("--rounds must be between 1 and 20")
    result = run_benchmark(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
