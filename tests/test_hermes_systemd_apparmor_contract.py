from __future__ import annotations

from pathlib import Path


CODER_ROOT = Path("deploy/hermes-coders")
UNIT_PATH = Path("deploy/systemd/hermes-coders.service")


def test_apparmor_allows_git_https_transport_helpers() -> None:
    profile = (CODER_ROOT / "security/apparmor-hermes-codex-bwrap").read_text(
        encoding="utf-8"
    )

    assert "/usr/bin/git ix," in profile
    assert "/usr/lib/git-core/git-remote-http ix," in profile
    assert "/usr/lib/git-core/git-remote-https ix," in profile


def test_current_runner_allows_git_helpers_and_codex_temp_only() -> None:
    profile = (CODER_ROOT / "security/apparmor-hermes-codex-runner").read_text(
        encoding="utf-8"
    )

    assert "/usr/lib/git-core/git ix," in profile
    assert "/usr/lib/git-core/git-remote-http ix," in profile
    assert "/usr/lib/git-core/git-remote-https ix," in profile
    assert "/usr/lib/git-core/** ix," not in profile
    assert "/opt/codex/** r," in profile
    assert "/opt/codex/tmp/ rw," in profile
    assert "/opt/codex/tmp/** rwk," in profile


def test_systemd_lifecycle_targets_only_coder_services() -> None:
    source = UNIT_PATH.read_text(encoding="utf-8")
    lines = source.splitlines()
    start = next(line for line in lines if line.startswith("ExecStart="))
    reload = next(
        line
        for line in lines
        if line.startswith("ExecReload=/usr/bin/docker compose")
    )
    stop = next(line for line in lines if line.startswith("ExecStop="))

    for command in (start, reload):
        assert " up -d " in command
        assert " --no-deps " in command
        assert " --no-build " in command
        assert command.endswith("hermes-coder-velvet hermes-coder-max")

    assert " stop --timeout 45 " in stop
    assert stop.endswith("hermes-coder-velvet hermes-coder-max")

    for command in (start, reload, stop):
        assert "hermes-chat-" not in command
        assert "db-proxy" not in command


def test_reconciler_installs_and_rolls_back_apparmor_profile() -> None:
    source = (CODER_ROOT / "reconcile_release_systemd.sh").read_text(
        encoding="utf-8"
    )

    assert "APPARMOR_TARGET=/etc/apparmor.d/hermes-codex-bwrap" in source
    assert "APPARMOR_PARSER=/usr/sbin/apparmor_parser" in source
    assert 'backup_if_present "$APPARMOR_TARGET" hermes-codex-bwrap.apparmor' in source
    assert 'install -o root -g root -m 0644 "$apparmor_source" "$APPARMOR_TARGET"' in source
    assert '"$APPARMOR_PARSER" -r "$APPARMOR_TARGET"' in source
    assert "restore_previous_apparmor()" in source
    assert '"$APPARMOR_PARSER" -R "$APPARMOR_TARGET"' in source

    rollback = source.split("rollback_units()", 1)[1].split(
        "trap rollback_units", 1
    )[0]
    assert rollback.index("restore_previous_apparmor") < rollback.index(
        "restore_previous_containers"
    )


def test_reconciler_fails_closed_without_git_https_rules() -> None:
    source = (CODER_ROOT / "reconcile_release_systemd.sh").read_text(
        encoding="utf-8"
    )

    assert "for helper in git-remote-http git-remote-https" in source
    assert 'grep -Fq "/usr/lib/git-core/$helper ix,"' in source
    assert "AppArmor profile не разрешает Git HTTPS helper" in source
