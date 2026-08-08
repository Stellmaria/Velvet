from __future__ import annotations

import argparse
import base64
import json
import math
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


BENCHMARK_CONTRACT_VERSION = 2
_REQUIRED_SCHEMA_KEYS = frozenset(
    {"subjects", "composition", "lighting", "palette", "confidence"}
)
_MEMORY_UNITS = {
    "b": 1,
    "kb": 1000,
    "kib": 1024,
    "mb": 1000**2,
    "mib": 1024**2,
    "gb": 1000**3,
    "gib": 1024**3,
    "tb": 1000**4,
    "tib": 1024**4,
}
_CONTAINER_REQUEST_SCRIPT = r"""
import json
import sys
import urllib.error
import urllib.request

request_data = json.load(sys.stdin)
payload = request_data.get("payload")
data = None if payload is None else json.dumps(payload).encode("utf-8")
request = urllib.request.Request(
    request_data["url"],
    data=data,
    headers={
        "Content-Type": "application/json",
        "X-Request-ID": "vision-benchmark",
    },
    method="GET" if payload is None else "POST",
)
try:
    with urllib.request.urlopen(request, timeout=float(request_data["timeout"])) as response:
        sys.stdout.buffer.write(response.read())
except urllib.error.HTTPError as error:
    detail = error.read().decode("utf-8", errors="replace")
    print(f"HTTP {error.code}: {detail[:1000]}", file=sys.stderr)
    raise SystemExit(3)
""".strip()


@dataclass(frozen=True, slots=True)
class RuntimeStats:
    memory_bytes: int | None = None
    cpu_percent: float | None = None
    host_swap_used_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class Sample:
    index: int
    latency_seconds: float | None
    response_chars: int
    schema_valid: bool
    completion_tokens: int | None = None
    tokens_per_second_estimate: float | None = None
    peak_runtime_memory_bytes: int | None = None
    peak_runtime_cpu_percent: float | None = None
    peak_host_swap_used_bytes: int | None = None
    error: str | None = None


def _request_json_direct(
    url: str,
    payload: dict[str, Any] | None,
    timeout: float,
) -> dict[str, Any]:
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


def _request_json_via_container(
    container: str,
    url: str,
    payload: dict[str, Any] | None,
    timeout: float,
) -> dict[str, Any]:
    request_data = json.dumps(
        {"url": url, "payload": payload, "timeout": timeout},
        separators=(",", ":"),
    )
    try:
        completed = subprocess.run(
            ["docker", "exec", "-i", container, "python", "-c", _CONTAINER_REQUEST_SCRIPT],
            input=request_data,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(30.0, timeout + 10.0),
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(
            f"Unable to execute benchmark request through container {container}."
        ) from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            f"Container request failed via {container}: {detail[:1000]}"
        )
    result = json.loads(completed.stdout)
    if not isinstance(result, dict):
        raise RuntimeError("Gateway returned a non-object JSON response.")
    return result


def _request_json(
    url: str,
    payload: dict[str, Any] | None,
    timeout: float,
    *,
    request_container: str = "",
) -> dict[str, Any]:
    if request_container:
        return _request_json_via_container(request_container, url, payload, timeout)
    return _request_json_direct(url, payload, timeout)


def _parse_memory_bytes(value: str | None) -> int | None:
    if not value:
        return None
    token = value.split("/", 1)[0].strip()
    if not token:
        return None
    number = []
    unit = []
    for char in token:
        if char.isdigit() or char in {".", ","}:
            number.append(char)
        elif not char.isspace():
            unit.append(char)
    if not number:
        return None
    try:
        amount = float("".join(number).replace(",", "."))
    except ValueError:
        return None
    multiplier = _MEMORY_UNITS.get("".join(unit).casefold())
    if multiplier is None:
        return None
    return int(amount * multiplier)


def _parse_percent(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.strip().removesuffix("%"))
    except ValueError:
        return None


def _host_swap_used_bytes() -> int | None:
    try:
        lines = Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    values: dict[str, int] = {}
    for line in lines:
        key, separator, raw = line.partition(":")
        if not separator:
            continue
        parts = raw.strip().split()
        if not parts:
            continue
        try:
            values[key] = int(parts[0]) * 1024
        except ValueError:
            continue
    if "SwapTotal" not in values or "SwapFree" not in values:
        return None
    return max(0, values["SwapTotal"] - values["SwapFree"])


def _docker_stats(container: str) -> RuntimeStats:
    if not container:
        return RuntimeStats(host_swap_used_bytes=_host_swap_used_bytes())
    try:
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
    except (OSError, subprocess.SubprocessError):
        return RuntimeStats(host_swap_used_bytes=_host_swap_used_bytes())
    if result.returncode != 0 or not result.stdout.strip():
        return RuntimeStats(host_swap_used_bytes=_host_swap_used_bytes())
    payload = json.loads(result.stdout.splitlines()[0])
    return RuntimeStats(
        memory_bytes=_parse_memory_bytes(str(payload.get("MemUsage") or "")),
        cpu_percent=_parse_percent(str(payload.get("CPUPerc") or "")),
        host_swap_used_bytes=_host_swap_used_bytes(),
    )


def _docker_image_identity(container: str) -> dict[str, Any] | None:
    if not container:
        return None
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{json .}}", container],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    payload = json.loads(result.stdout)
    if not isinstance(payload, Mapping):
        return None
    config = payload.get("Config")
    image_ref = str(config.get("Image") or "") if isinstance(config, Mapping) else ""
    image_id = str(payload.get("Image") or "").strip()
    repo_digests: list[str] = []
    if image_id:
        try:
            image_result = subprocess.run(
                [
                    "docker",
                    "image",
                    "inspect",
                    "--format",
                    "{{json .RepoDigests}}",
                    image_id,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            image_result = None
        if image_result is not None and image_result.returncode == 0 and image_result.stdout.strip():
            parsed = json.loads(image_result.stdout)
            if isinstance(parsed, list):
                repo_digests = [str(item) for item in parsed if str(item).strip()]
    return {
        "container": container,
        "image_ref": image_ref or None,
        "image_id": image_id or None,
        "repo_digests": repo_digests,
    }


def _sample_stats_while_running(
    container: str,
    stop: threading.Event,
    samples: list[RuntimeStats],
) -> None:
    while not stop.wait(0.5):
        try:
            samples.append(_docker_stats(container))
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            continue


def _extract_content(response: Mapping[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Gateway response has no choices.")
    first = choices[0]
    if not isinstance(first, Mapping):
        raise RuntimeError("Gateway choice is invalid.")
    message = first.get("message")
    if not isinstance(message, Mapping):
        raise RuntimeError("Gateway choice has no message.")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Gateway returned an empty response.")
    return content


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].strip().casefold() in {"```", "```json"}:
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _schema_valid(content: str) -> bool:
    try:
        payload = json.loads(_strip_json_fence(content))
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, Mapping):
        return False
    if not _REQUIRED_SCHEMA_KEYS.issubset(payload):
        return False
    if not isinstance(payload.get("subjects"), list):
        return False
    if not isinstance(payload.get("palette"), list):
        return False
    if not isinstance(payload.get("composition"), str):
        return False
    if not isinstance(payload.get("lighting"), str):
        return False
    confidence = payload.get("confidence")
    return (
        isinstance(confidence, (int, float))
        and not isinstance(confidence, bool)
        and 0 <= float(confidence) <= 100
    )


def _completion_tokens(response: Mapping[str, Any]) -> int | None:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return None
    value = usage.get("completion_tokens")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    return value


def _build_payload(
    *,
    model: str,
    data_uri: str,
    max_output_tokens: int,
) -> dict[str, Any]:
    return {
        "model": model,
        "stream": False,
        "temperature": 0,
        "max_tokens": max_output_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Return only one JSON object, no markdown. Required keys: "
                            "subjects (array of strings), composition (string), "
                            "lighting (string), palette (array of strings), "
                            "confidence (integer 0-100). Describe only visible facts."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ],
    }


def _peak(values: list[float | int | None]) -> float | int | None:
    available = [value for value in values if value is not None]
    return max(available) if available else None


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _sample_resource_peaks(
    stats: list[RuntimeStats],
) -> tuple[int | None, float | None, int | None]:
    if not stats:
        return None, None, None
    memory = _peak([item.memory_bytes for item in stats])
    cpu = _peak([item.cpu_percent for item in stats])
    swap = _peak([item.host_swap_used_bytes for item in stats])
    return (
        int(memory) if memory is not None else None,
        float(cpu) if cpu is not None else None,
        int(swap) if swap is not None else None,
    )


def _unload_model(container: str, model: str) -> None:
    if not container:
        raise RuntimeError("--cold-unload requires --docker-container.")
    try:
        result = subprocess.run(
            ["docker", "exec", container, "ollama", "stop", model],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("Unable to execute cold model unload.") from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Unable to unload model before cold sample: {detail[:500]}")


def _read_image_data_uri(path: str, max_input_bytes: int) -> str:
    image_path = Path(path)
    image_bytes = image_path.read_bytes()
    if len(image_bytes) > max_input_bytes:
        raise RuntimeError("Input image exceeds --max-input-bytes.")
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(image_path.suffix.casefold())
    if mime is None:
        raise RuntimeError("Benchmark image must be JPEG, PNG or WebP.")
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"


def _digest_matches(actual: str, expected: str) -> bool:
    return actual.casefold().startswith(expected.casefold())


def _summary(samples: list[Sample]) -> dict[str, Any]:
    successful = [sample for sample in samples if sample.error is None]
    warm_latencies = [
        sample.latency_seconds
        for sample in successful
        if sample.index > 1 and sample.latency_seconds is not None
    ]
    if not warm_latencies:
        warm_latencies = [
            sample.latency_seconds
            for sample in successful
            if sample.latency_seconds is not None
        ]
    token_rates = [
        sample.tokens_per_second_estimate
        for sample in successful
        if sample.tokens_per_second_estimate is not None
    ]
    cold_latency = (
        samples[0].latency_seconds if samples and samples[0].error is None else None
    )
    schema_valid = sum(1 for sample in successful if sample.schema_valid)
    return {
        "cold_latency_seconds": cold_latency,
        "warm_p50_seconds": (
            round(value, 3)
            if (value := _percentile(warm_latencies, 0.50)) is not None
            else None
        ),
        "warm_p95_seconds": (
            round(value, 3)
            if (value := _percentile(warm_latencies, 0.95)) is not None
            else None
        ),
        "success_rate": round(len(successful) / len(samples), 4) if samples else 0.0,
        "failure_rate": (
            round((len(samples) - len(successful)) / len(samples), 4)
            if samples
            else 0.0
        ),
        "schema_validity_rate": (
            round(schema_valid / len(successful), 4) if successful else 0.0
        ),
        "median_tokens_per_second_estimate": (
            round(float(_percentile(token_rates, 0.50)), 3) if token_rates else None
        ),
        "peak_runtime_memory_bytes": _peak(
            [sample.peak_runtime_memory_bytes for sample in samples]
        ),
        "peak_runtime_cpu_percent": _peak(
            [sample.peak_runtime_cpu_percent for sample in samples]
        ),
        "peak_host_swap_used_bytes": _peak(
            [sample.peak_host_swap_used_bytes for sample in samples]
        ),
    }


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    endpoint = args.endpoint.rstrip("/")
    health = _request_json(
        f"{endpoint}/health",
        None,
        args.timeout,
        request_container=args.request_container,
    )
    health_model = str(health.get("model") or "").strip()
    model = args.model.strip() or health_model
    if not model:
        raise RuntimeError("Model is missing from health response and arguments.")
    if health_model and model != health_model:
        raise RuntimeError(
            f"Gateway model mismatch: expected {model}, health reports {health_model}."
        )

    digest = str(health.get("digest") or "").strip()
    if args.expected_digest:
        if not digest or not _digest_matches(digest, args.expected_digest):
            raise RuntimeError(
                "Gateway model digest mismatch: "
                f"expected prefix {args.expected_digest}, got {digest or '<missing>'}."
            )

    data_uri = _read_image_data_uri(args.image, args.max_input_bytes)
    payload = _build_payload(
        model=model,
        data_uri=data_uri,
        max_output_tokens=args.max_output_tokens,
    )
    runtime_identity = _docker_image_identity(args.docker_container)

    if args.cold_unload:
        _unload_model(args.docker_container, model)

    samples: list[Sample] = []
    for index in range(args.rounds):
        stats: list[RuntimeStats] = []
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
        try:
            response = _request_json(
                f"{endpoint}/v1/chat/completions",
                payload,
                args.timeout,
                request_container=args.request_container,
            )
            latency = time.monotonic() - started
            content = _extract_content(response)
            completion_tokens = _completion_tokens(response)
            tokens_per_second = (
                completion_tokens / latency
                if completion_tokens is not None and latency > 0
                else None
            )
            error = None
            schema_valid = _schema_valid(content)
            response_chars = len(content)
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            latency = None
            completion_tokens = None
            tokens_per_second = None
            error = str(exc)
            schema_valid = False
            response_chars = 0
        finally:
            stop.set()
            if monitor is not None:
                monitor.join(timeout=2)
        if not stats:
            stats.append(_docker_stats(args.docker_container))
        memory, cpu, swap = _sample_resource_peaks(stats)
        samples.append(
            Sample(
                index=index + 1,
                latency_seconds=round(latency, 3) if latency is not None else None,
                response_chars=response_chars,
                schema_valid=schema_valid,
                completion_tokens=completion_tokens,
                tokens_per_second_estimate=(
                    round(tokens_per_second, 3)
                    if tokens_per_second is not None
                    else None
                ),
                peak_runtime_memory_bytes=memory,
                peak_runtime_cpu_percent=cpu,
                peak_host_swap_used_bytes=swap,
                error=error,
            )
        )

    result = {
        "benchmark_contract_version": BENCHMARK_CONTRACT_VERSION,
        "endpoint": endpoint,
        "request_container": args.request_container or None,
        "model": model,
        "digest": digest or None,
        "expected_digest": args.expected_digest or None,
        "max_output_tokens": args.max_output_tokens,
        "rounds": args.rounds,
        "cold_unload_requested": bool(args.cold_unload),
        "runtime_image": runtime_identity,
        **_summary(samples),
        "samples": [asdict(sample) for sample in samples],
        "manual_scorecard": {
            "omissions": None,
            "hallucinations": None,
            "visual_quality_accuracy": None,
            "ocr_accuracy": None,
            "pose_accuracy": None,
            "composition_accuracy": None,
            "owner_quality_score": None,
        },
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
    parser.add_argument("--request-container", default="")
    parser.add_argument("--image", required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--expected-digest", default="")
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--max-input-bytes", type=int, default=25 * 1024 * 1024)
    parser.add_argument("--docker-container", default="velvet-vision-runtime-1")
    parser.add_argument("--cold-unload", action="store_true")
    parser.add_argument("--output", default="")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.rounds < 1 or args.rounds > 20:
        raise SystemExit("--rounds must be between 1 and 20")
    if args.max_output_tokens < 64 or args.max_output_tokens > 2048:
        raise SystemExit("--max-output-tokens must be between 64 and 2048")
    result = run_benchmark(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
