# Telegram shared helper inventory

Issue: #419

## Machine contract

Reproducible inventory:

```bash
python scripts/inventory_telegram_helpers.py --check
python scripts/inventory_telegram_helpers.py --json
```

The scanner covers production Python under `velvet_bot/`, fingerprints non-trivial
function bodies, classifies exact clones and rejects new private helper imports between
Telegram router modules.

Allowed duplicate classifications:

- `real-duplicate` — behavior belongs to an explicit shared presentation/service contract;
- `generated/compat` — generated, migration, legacy transport or compatibility surface;
- `allowed-template` — structurally repeated code whose policy remains local.

## Public contracts

| Helper family | Canonical contract | Boundary |
| --- | --- | --- |
| safe edit/send fallback | `presentation.telegram.shared.editing` | Telegram transport only; ignores only `message is not modified` |
| pagination keyboards | `presentation.telegram.shared.navigation` | one-based page navigation without repository/domain decisions |
| deletion helpers | `presentation.telegram.shared.deletion` | explicit best-effort deletion |
| media download/preview/original delivery | `image_preview`, `public_archive_display` | media transport and Telegram file delivery |
| callback navigation/back buttons | `presentation.telegram.shared.navigation` | callback payloads are supplied by the caller |
| owner/editor/member guards | `core.access`, `presentation.telegram.runtime_contracts` | access policy remains outside generic UI helpers |
| worker compensation/reporting | `domains.media_generation.worker`, `friendly_worker` | worker lifecycle owns compensation and reporting |
| message chunking/HTML fallback | `presentation.telegram.shared.text` | Telegram length and parse-mode resilience only |
| progress-card updates | `app.telegram_progress_resilience` | task execution is independent from Telegram progress edits |

## Hard boundaries

Files under `velvet_bot/presentation/telegram/shared/` may not:

- import repositories, database modules or domain packages;
- contain SQL query text;
- decide owner/editor/member permissions;
- perform charging, compensation or provider routing.

Controllers may consume public helpers, but may not import helper-like private names from
neighbouring router modules. Assembly facades and compatibility imports are tracked by the
separate runtime/root-module contracts and are not silently treated as shared helpers.

## Migration rule

Each helper family moves independently. Callback payloads, user-visible text, SQL,
permissions and business behavior are kept unchanged in the same slice. Regression tests
must preserve Telegram error handling and callback data before a local helper is removed.
