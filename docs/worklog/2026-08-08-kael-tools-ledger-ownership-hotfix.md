# Kael tools and coder ledger ownership hotfix

Date: 2026-08-08

## Incident

Production Hermes remained healthy, and `coderctl health all` returned authenticated coder capabilities, but Kael could not execute canonical operator tools after orchestration reconciliation. Inside the Hermes container the persisted data directory was owned by the Hermes runtime UID/GID `10000:10000`, while `/opt/data/tools` and `coderctl.py` had been reassigned to the host service user's `1000:1000` ownership. With mode `0750` on the directory and `0500` on `coderctl.py`, UID 10000 received `Permission denied`.

The same orchestration installer also reassigned `/opt/data/orchestration` to the host service user. That is more dangerous than the health symptom because `coderctl submit` sends a run to the central router before persisting its local task ledger. A writable router with an unwritable local ledger can therefore create an upstream run that Kael cannot record or subsequently address by task ID.

## Root cause

`deploy/hermes-orchestration/install.sh` derived ownership from `VELVET_DATA_DIR` instead of from the existing Hermes data directory. On production those owners differ: the application data parent belongs to the host service user, while the bind-mounted Hermes data directory belongs to the container runtime identity.

## Fix

- Derive `hermes_uid` and `hermes_gid` from the existing `$hermes_data` directory.
- Preserve those owners for `$hermes_data/tools`, `$hermes_data/orchestration`, and the installed `coderctl.py`.
- Fail closed if the expected Hermes data directory does not exist instead of recreating it under an unrelated owner.
- Add `Ledger.ensure_writable()` to `coderctl.py` and run it before the first router submit. The preflight validates the ledger/lock can be accessed and that the ledger directory supports the temporary-file/replace write pattern used by persistence.
- Add regression coverage proving orchestration ownership comes from `$hermes_data`, and proving an unwritable ledger prevents any router submit.

## Production evidence before the fix

Observed inside `velvet-hermes-1`:

```text
10000:10000 700 /opt/data
1000:1000 750 /opt/data/tools
10000:10000 500 /opt/data/tools/opsctl.py
10000:10000 500 /opt/data/tools/monitorctl.py
10000:10000 500 /opt/data/tools/reconcilectl.py
1000:1000 500 /opt/data/tools/coderctl.py
```

A bounded runtime repair restored `/opt/data/tools` and `coderctl.py` to `10000:10000`; execution as the Hermes user then returned `KAEL_TOOLS_OK`. The repository fix prevents the next orchestration installation from reintroducing the ownership mismatch.

## Safety

This change does not broaden Kael permissions, grant production privileges to coder agents, alter router authentication, or weaken fail-closed delegation. It restores the existing Hermes runtime ownership boundary and adds a pre-submit local durability gate.
