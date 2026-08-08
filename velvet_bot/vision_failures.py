from __future__ import annotations

import asyncio
from enum import StrEnum

from velvet_bot.ai_vision import VisionAnalysisError, VisionProviderUnavailable


class VisionFailureKind(StrEnum):
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    TRANSPORT = "transport"
    OOM = "oom"
    PROVIDER = "provider_error"
    SCHEMA = "invalid_schema"
    REFUSAL = "refusal"
    ANALYSIS = "analysis_error"


class _FailureMixin:
    kind: VisionFailureKind = VisionFailureKind.ANALYSIS
    retryable: bool = False
    full_image_retryable: bool = False
    permanent: bool = False

    def __str__(self) -> str:
        raw = super().__str__()
        prefix = f"[{self.kind.value}]"
        return raw if raw.startswith(prefix) else f"{prefix} {raw}"


class VisionTimeoutError(_FailureMixin, VisionProviderUnavailable):
    kind = VisionFailureKind.TIMEOUT
    retryable = True
    # A second 300-second image request is precisely the retry storm we are avoiding.
    full_image_retryable = False


class VisionTransportError(_FailureMixin, VisionProviderUnavailable):
    kind = VisionFailureKind.TRANSPORT
    retryable = True
    full_image_retryable = True


class VisionOutOfMemoryError(_FailureMixin, VisionAnalysisError):
    kind = VisionFailureKind.OOM
    permanent = True


class VisionProviderError(_FailureMixin, VisionAnalysisError):
    kind = VisionFailureKind.PROVIDER
    permanent = True


class VisionSchemaError(_FailureMixin, VisionAnalysisError):
    kind = VisionFailureKind.SCHEMA
    permanent = True


class VisionRefusalError(_FailureMixin, VisionAnalysisError):
    kind = VisionFailureKind.REFUSAL
    permanent = True


_OOM_MARKERS = (
    "out of memory",
    "insufficient memory",
    "not enough memory",
    "failed to allocate",
    "cannot allocate memory",
    "cuda oom",
    "cuda out of memory",
    "model requires more system memory",
)
_TIMEOUT_MARKERS = (
    "timed out",
    "timeout",
    "deadline exceeded",
    "gateway timeout",
    "local vl runtime timed out",
)
_REFUSAL_MARKERS = (
    "provider refusal",
    "content policy",
    "safety policy",
    "request was blocked",
    "content was blocked",
    "cannot analyze this image",
    "can't analyze this image",
)


def _contains(text: str, markers: tuple[str, ...]) -> bool:
    normalized = text.casefold()
    return any(marker in normalized for marker in markers)


def classify_http_failure(*, status: int, detail: str) -> VisionAnalysisError:
    message = f"HTTP {int(status)}: {detail or 'ошибка VL provider'}"
    if _contains(message, _OOM_MARKERS):
        return VisionOutOfMemoryError(message)
    if status in {408, 504} or _contains(message, _TIMEOUT_MARKERS):
        return VisionTimeoutError(message)
    if _contains(message, _REFUSAL_MARKERS):
        return VisionRefusalError(message)
    if status in {429, 500, 502, 503}:
        return VisionTransportError(message)
    return VisionProviderError(message)


def classify_payload_failure(detail: str) -> VisionAnalysisError:
    message = detail.strip() or "VL provider вернул ошибку без описания."
    if _contains(message, _OOM_MARKERS):
        return VisionOutOfMemoryError(message)
    if _contains(message, _TIMEOUT_MARKERS):
        return VisionTimeoutError(message)
    if _contains(message, _REFUSAL_MARKERS):
        return VisionRefusalError(message)
    return VisionProviderError(message)


def schema_failure(error: BaseException | str) -> VisionSchemaError:
    message = str(error).strip() or "VL provider вернул невалидный structured output."
    if isinstance(error, VisionSchemaError):
        return error
    return VisionSchemaError(message)


def failure_kind(error: BaseException) -> VisionFailureKind:
    if isinstance(error, asyncio.CancelledError):
        return VisionFailureKind.CANCELLED
    kind = getattr(error, "kind", None)
    if isinstance(kind, VisionFailureKind):
        return kind
    if isinstance(error, VisionProviderUnavailable):
        return VisionFailureKind.TRANSPORT
    if isinstance(error, VisionAnalysisError):
        return VisionFailureKind.ANALYSIS
    return VisionFailureKind.ANALYSIS


def is_full_image_retryable(error: BaseException) -> bool:
    return bool(getattr(error, "full_image_retryable", False))


def is_permanent_vision_failure(error: BaseException) -> bool:
    if bool(getattr(error, "permanent", False)):
        return True
    if not isinstance(error, VisionAnalysisError):
        return False
    message = str(error).casefold()
    return "прочитать как изображение" in message or "file is too big" in message


__all__ = (
    "VisionFailureKind",
    "VisionOutOfMemoryError",
    "VisionProviderError",
    "VisionRefusalError",
    "VisionSchemaError",
    "VisionTimeoutError",
    "VisionTransportError",
    "classify_http_failure",
    "classify_payload_failure",
    "failure_kind",
    "is_full_image_retryable",
    "is_permanent_vision_failure",
    "schema_failure",
)
