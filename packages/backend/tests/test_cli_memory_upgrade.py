"""CLI migration command dispatch must not shadow its imported upgrade function."""

from app import cli


def test_upgrade_command_calls_migration(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(cli, "upgrade_to_head", lambda: called.append(True))
    monkeypatch.setattr(cli, "current_revision", lambda: "test-revision")

    assert cli.main(["upgrade"]) == 0
    assert called == [True]
    assert "test-revision" in capsys.readouterr().out
