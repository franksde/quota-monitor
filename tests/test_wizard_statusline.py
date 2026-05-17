import json
from unittest.mock import patch

from quota_monitor.cli.setup import _statusline_wizard_step


def test_statusline_step_fresh_install_accept(tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"permissions": {}}))
    backup_path = tmp_path / "statusline_original.json"

    with patch("quota_monitor.cli.setup.ask_yes_no", return_value=True):
        _statusline_wizard_step(
            settings_path=settings_path,
            backup_path=backup_path,
        )

    settings = json.loads(settings_path.read_text())
    assert "quota_monitor.statusline" in settings["statusLine"]["command"]
    assert backup_path.exists()


def test_statusline_step_fresh_install_decline(tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"permissions": {}}))
    backup_path = tmp_path / "statusline_original.json"

    with patch("quota_monitor.cli.setup.ask_yes_no", return_value=False):
        _statusline_wizard_step(
            settings_path=settings_path,
            backup_path=backup_path,
        )

    settings = json.loads(settings_path.read_text())
    assert "statusLine" not in settings
    assert not backup_path.exists()


def test_statusline_step_existing_tool_accept(tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({
        "statusLine": {"type": "command", "command": "~/.open-island/bin/oi"},
    }))
    backup_path = tmp_path / "statusline_original.json"

    with patch("quota_monitor.cli.setup.ask_yes_no", return_value=True):
        _statusline_wizard_step(
            settings_path=settings_path,
            backup_path=backup_path,
        )

    settings = json.loads(settings_path.read_text())
    assert "quota_monitor.statusline" in settings["statusLine"]["command"]
    backup = json.loads(backup_path.read_text())
    assert backup["original"]["command"] == "~/.open-island/bin/oi"


def test_statusline_step_already_configured(tmp_path, capsys):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({
        "statusLine": {"type": "command", "command": "python3 -m quota_monitor.statusline"},
    }))
    backup_path = tmp_path / "statusline_original.json"

    _statusline_wizard_step(
        settings_path=settings_path,
        backup_path=backup_path,
    )

    captured = capsys.readouterr()
    assert "already configured" in captured.out.lower() or "已配置" in captured.out
