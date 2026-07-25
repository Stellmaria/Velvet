# Workspace media policy controller extraction

Date: 2026-07-25
Status: completed

## Context

`workspace_owner_controls.py` still owns the broad `wpa` personal archive callback,
including navigation, media actions, download policy, visibility mutations and deletion.
Earlier slices made workspace home, archive dashboard, reference dashboard and workspace
deletion canonical outside that router. The archive dashboard still imported
`WorkspacePersonalArchiveCallback` from the legacy module, and media policy actions were
still executed only by its catch-all handler.

## Change

This slice adds `workspace_personal_archive_contract.py` with:

- a typed immutable `WorkspacePersonalArchiveAction`;
- a stable `workspace_personal_archive_callback` builder;
- a strict parser for the existing six-part `wpa` payload;
- a custom aiogram filter that selects actions without declaring a second
  `CallbackData` class for the same prefix.

`workspace_media_policy_controller.py` now owns:

- the media access/download presentation and keyboard;
- the card help screen;
- `settings`, `mediahelp` and no-op header callbacks;
- download audience actions `dlaudnone`, `dlaudall`, `dlaudsub`;
- download variant actions `dlvarwm`, `dlvarorig`;
- owner checks, archive module checks and stale media protection;
- dependency validation for subscriber channels, watermark template and watermark
  storage;
- persistence through `WorkspaceProductService.set_download_policy`.

The existing archive registrar installs these handlers before
`workspace_owner_controls_router`, so the legacy catch-all no longer receives those
actions at runtime.

`workspace_archive_dashboard.py` now builds `wpa` payloads through the public contract
and has no import from `workspace_owner_controls.py`.

## Compatibility

The callback wire format remains:

`wpa:<action>:<workspace_id>:<character_id>:<offset>:<media_id>`

No migration is required. Existing Telegram buttons continue to work. Policy labels,
validation messages, owner-only access, media freshness checks and SQL/service behavior
are preserved.

## Regression coverage

`tests/test_workspace_media_policy_contract.py` covers:

- exact callback round-trip and invalid payload rejection;
- policy keyboard selections and return navigation;
- a ready-to-render policy presentation with connected dependencies;
- removal of the archive dashboard dependency on the legacy owner router;
- controller ownership of policy actions;
- bundle-level registration before `workspace_owner_controls_router`.

## Next slice

Extract personal archive navigation/rendering (`open`, `show`, `close`, `empty`, `help`)
and then separate owner media mutations from delete/download delivery. Once those
handlers are canonical, the unreachable blocks can be deleted mechanically from
`workspace_owner_controls.py`.
