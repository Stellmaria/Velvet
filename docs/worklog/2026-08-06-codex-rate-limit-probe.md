# Codex rate-limit probe repair

Date: 2026-08-06

## Incident

`GET /v1/rate-limits` returned HTTP 500 from the internal Codex runner. The
orchestration router surfaced that as HTTP 502 with only
`Internal runner error: RuntimeError`, while GPT Image 2 generation itself
continued to work.

## Root cause

The probe combined `selectors` with a buffered text-mode `stdout.readline()`.
When Codex app-server emitted the `account/read` and `account/rateLimits/read`
responses in one write, `readline()` could prefetch both lines. The second line
then lived in Python's userspace buffer while `select()` waited for new kernel
readability until timeout.

The probe also trusted provider names `primary` and `secondary` as UI semantics.
Codex can expose only a long weekly bucket in `primary`, which would otherwise
be shown as the short window.

## Change

- use unbuffered binary pipes and an explicit JSONL byte buffer;
- drain all complete buffered lines before waiting on the selector;
- drain and redact app-server stderr;
- preserve sanitized JSON-RPC error details;
- retry the bounded read once for transient app-server failures;
- classify short and long windows by duration;
- map probe failures to a meaningful HTTP 502 RunnerError;
- add a fake app-server regression that writes both responses in one chunk.

## Verification

- `python -m unittest tests.test_codex_runner_rate_limits`
- `python -m compileall -q deploy/hermes-coders/codex_runner.py tests/test_codex_runner_rate_limits.py`
