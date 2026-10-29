"""Tests for the ``cpractice`` start/open/problems/version commands.

The commands are deliberately boring: reuse a running CPractice, refuse a
non-loopback bind without consent, record the last address, and never start a
second server on an occupied port.
"""

from __future__ import annotations

import json

from app import cli


def test_non_loopback_requires_allow_lan(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "is_windows", lambda: False)
    assert cli.main(["start", "--host", "0.0.0.0"]) == 2
    assert "--allow-lan" in capsys.readouterr().out


def test_existing_cpractice_is_reused(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CPRACTICE_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "is_windows", lambda: False)
    monkeypatch.setattr(cli, "server_is_cpractice", lambda url: True)
    monkeypatch.setattr(cli, "open_browser", lambda url: None)

    def must_not_start(app, host, port):
        raise AssertionError("must not start")

    monkeypatch.setattr(cli, "_run_server", must_not_start)
    assert cli.main(["start"]) == 0


def test_start_records_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CPRACTICE_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "is_windows", lambda: False)
    monkeypatch.setattr(cli, "server_is_cpractice", lambda url: False)
    monkeypatch.setattr(cli, "port_is_free", lambda host, port: True)
    monkeypatch.setattr(cli, "open_browser", lambda url: None)
    monkeypatch.setattr(cli, "_run_server", lambda app, host, port: None)
    assert cli.main(["start", "--port", "9123", "--no-browser"]) == 0
    assert json.loads((tmp_path / "state.json").read_text()) == {
        "host": "127.0.0.1",
        "port": 9123,
    }
