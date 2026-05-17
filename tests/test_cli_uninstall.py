import json
from unittest.mock import patch
from quota_monitor.cli.uninstall import uninstall


def test_uninstall_calls_launchagent_remove(tmp_path):
    plist = tmp_path / "agent.plist"
    plist.write_text("<plist/>")
    with patch("quota_monitor.cli.uninstall.uninstall_launch_agent") as remove, \
         patch("quota_monitor.cli.uninstall.platform_paths") as mock_paths:
        mock_paths.claude_settings_file.return_value = tmp_path / "settings.json"
        mock_paths.statusline_original.return_value = tmp_path / "statusline_original.json"
        mock_paths.rate_limits_cache.return_value = tmp_path / "rate_limits_cache.json"
        mock_paths.calibration_file.return_value = tmp_path / "calibration.json"
        rc = uninstall(launch_agent_label="io.x", plist_path=plist)
    assert rc == 0
    remove.assert_called_once_with(plist_path=plist)


def test_uninstall_is_noop_when_plist_missing(tmp_path, capsys):
    plist = tmp_path / "no.plist"
    with patch("quota_monitor.cli.uninstall.platform_paths") as mock_paths:
        mock_paths.claude_settings_file.return_value = tmp_path / "settings.json"
        mock_paths.statusline_original.return_value = tmp_path / "statusline_original.json"
        mock_paths.rate_limits_cache.return_value = tmp_path / "rate_limits_cache.json"
        mock_paths.calibration_file.return_value = tmp_path / "calibration.json"
        rc = uninstall(launch_agent_label="io.x", plist_path=plist)
    assert rc == 0
    out = capsys.readouterr().out + capsys.readouterr().err
    # The function should still print guidance about config/state.
    assert "config" in (out.lower() + "")


def test_uninstall_restores_statusline(tmp_path, capsys):
    plist_path = tmp_path / "agent.plist"
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({
        "statusLine": {"type": "command", "command": "python3 -m quota_monitor.statusline"},
        "other": "preserved",
    }))
    backup_path = tmp_path / "statusline_original.json"
    backup_path.write_text(json.dumps({"original": {"type": "command", "command": "echo hi"}}))
    cache_path = tmp_path / "rate_limits_cache.json"
    cache_path.write_text("{}")
    calibration_path = tmp_path / "calibration.json"
    calibration_path.write_text("{}")

    with patch("quota_monitor.cli.uninstall.platform_paths") as mock_paths:
        mock_paths.claude_settings_file.return_value = settings_path
        mock_paths.statusline_original.return_value = backup_path
        mock_paths.rate_limits_cache.return_value = cache_path
        mock_paths.calibration_file.return_value = calibration_path

        rc = uninstall(launch_agent_label="test", plist_path=plist_path)

    assert rc == 0
    settings = json.loads(settings_path.read_text())
    assert settings["statusLine"]["command"] == "echo hi"
    assert settings["other"] == "preserved"
    assert not cache_path.exists()
    assert not backup_path.exists()
    assert not calibration_path.exists()
    captured = capsys.readouterr()
    assert "restored" in captured.out.lower() or "已恢复" in captured.out
