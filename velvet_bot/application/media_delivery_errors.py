from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum

from velvet_bot.application.media_delivery_models import MediaUrlExpired


class MediaDeliveryFailureKind(StrEnum):
    TRANSIENT = "transient"
    TERMINAL = "terminal"
    PROGRAMMING = "programming"


@dataclass(frozen=True, slots=True)
class MediaDeliveryFailure:
    code: str
    kind: MediaDeliveryFailureKind
    fingerprint: str
    public_message: str
    phase: str

    @property
    def retryable(self) -> bool:
        return self.kind is MediaDeliveryFailureKind.TRANSIENT

    def as_json(self) -> str:
        return json.dumps(
            {
                "code": self.code,
                "fingerprint": self.fingerprint,
                "kind": self.kind.value,
                "message": self.public_message,
                "phase": self.phase,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


class MediaDeliveryTransientError(RuntimeError):
    def __init__(self, code: str, public_message: str) -> None:
        self.code = _token(code, fallback="transient_error")
        self.public_message = str(public_message or "").strip() or _TRANSIENT_MESSAGE
        super().__init__(self.public_message)


class MediaDeliveryTerminalError(RuntimeError):
    def __init__(self, code: str, public_message: str) -> None:
        self.code = _token(code, fallback="terminal_error")
        self.public_message = str(public_message or "").strip() or _TERMINAL_MESSAGE
        super().__init__(self.public_message)


class MediaDeliveryInvariantError(RuntimeError):
    """A programming or state-machine invariant failure that must not be swallowed."""


class MediaDeliveryRecordedError(RuntimeError):
    """Safe durable wrapper carrying no provider URL, chat ID or user content."""

    def __init__(self, failure: MediaDeliveryFailure) -> None:
        self.failure = failure
        super().__init__(failure.public_message)


_TRANSIENT_MESSAGE = (
    "Временная ошибка доставки. Повтор будет выполнен из сохранённого состояния."
)
_TERMINAL_MESSAGE = "Сохранённый результат нельзя доставить автоматически."
_PROGRAMMING_MESSAGE = "Внутренняя ошибка состояния доставки."
_TOKEN_RE = re.compile(r"[^a-z0-9_]+")
_PROGRAMMING_ERRORS = (
    AssertionError,
    AttributeError,
    MediaDeliveryInvariantError,
    NotImplementedError,
    TypeError,
)
_TRANSIENT_ERRORS = (ConnectionError, OSError, TimeoutError)
_TRANSIENT_MODULE_PREFIXES = (
    "aiogram.",
    "aiohttp.",
    "asyncpg.",
    "httpx.",
    "urllib.",
)


def classify_media_delivery_error(
    error: BaseException,
    *,
    phase: str,
) -> MediaDeliveryFailure:
    if isinstance(error, MediaDeliveryRecordedError):
        return error.failure

    safe_phase = _token(phase, fallback="delivery")
    if isinstance(error, MediaDeliveryTransientError):
        code = error.code
        kind = MediaDeliveryFailureKind.TRANSIENT
        message = error.public_message
    elif isinstance(error, MediaDeliveryTerminalError):
        code = error.code
        kind = MediaDeliveryFailureKind.TERMINAL
        message = error.public_message
    elif isinstance(error, MediaUrlExpired):
        code = "provider_url_expired"
        kind = MediaDeliveryFailureKind.TERMINAL
        message = "Срок действия сохранённого URL результата истёк."
    elif isinstance(error, _PROGRAMMING_ERRORS):
        code = "programming_error"
        kind = MediaDeliveryFailureKind.PROGRAMMING
        message = _PROGRAMMING_MESSAGE
    elif isinstance(error, (KeyError, ValueError)):
        code = "invalid_delivery_data"
        kind = MediaDeliveryFailureKind.TERMINAL
        message = _TERMINAL_MESSAGE
    elif isinstance(error, _TRANSIENT_ERRORS):
        code = "transport_unavailable"
        kind = MediaDeliveryFailureKind.TRANSIENT
        message = _TRANSIENT_MESSAGE
    elif type(error).__module__.startswith(_TRANSIENT_MODULE_PREFIXES):
        code = "external_service_error"
        kind = MediaDeliveryFailureKind.TRANSIENT
        message = _TRANSIENT_MESSAGE
    elif isinstance(error, RuntimeError):
        # Existing provider/Telegram adapters historically use RuntimeError for
        # operational failures. State invariants use MediaDeliveryInvariantError.
        code = "operational_runtime_error"
        kind = MediaDeliveryFailureKind.TRANSIENT
        message = _TRANSIENT_MESSAGE
    else:
        code = "unexpected_error"
        kind = MediaDeliveryFailureKind.PROGRAMMING
        message = _PROGRAMMING_MESSAGE

    fingerprint_source = (
        f"{safe_phase}|{type(error).__module__}.{type(error).__qualname__}|{code}"
    )
    fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()[:20]
    return MediaDeliveryFailure(
        code=code,
        kind=kind,
        fingerprint=fingerprint,
        public_message=message,
        phase=safe_phase,
    )


def recorded_media_delivery_error(
    error: BaseException,
    *,
    phase: str,
) -> MediaDeliveryRecordedError:
    if isinstance(error, MediaDeliveryRecordedError):
        return error
    return MediaDeliveryRecordedError(
        classify_media_delivery_error(error, phase=phase)
    )


def media_delivery_error_fields(
    error: BaseException | None,
    *,
    phase: str,
) -> tuple[str | None, str | None, str | None]:
    if error is None:
        return None, None, None
    failure = classify_media_delivery_error(error, phase=phase)
    return failure.public_message, failure.code, failure.fingerprint


def media_delivery_error_text(
    error: BaseException | None,
    *,
    phase: str,
) -> str | None:
    if error is None:
        return None
    return classify_media_delivery_error(error, phase=phase).as_json()[:4000]


def raise_if_programming_error(error: BaseException, *, phase: str) -> None:
    failure = classify_media_delivery_error(error, phase=phase)
    if failure.kind is MediaDeliveryFailureKind.PROGRAMMING:
        raise error


def _token(value: object, *, fallback: str) -> str:
    text = _TOKEN_RE.sub("_", str(value or "").strip().casefold()).strip("_")
    return (text or fallback)[:96]


__all__ = (
    "MediaDeliveryFailure",
    "MediaDeliveryFailureKind",
    "MediaDeliveryInvariantError",
    "MediaDeliveryRecordedError",
    "MediaDeliveryTerminalError",
    "MediaDeliveryTransientError",
    "classify_media_delivery_error",
    "media_delivery_error_fields",
    "media_delivery_error_text",
    "raise_if_programming_error",
    "recorded_media_delivery_error",
)
