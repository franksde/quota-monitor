from unittest.mock import patch
from quota_monitor.cli.uninstall import uninstall


def test_uninstall_calls_launchagent_remove(tmp_path):
    plist = tmp_path / "agent.plist"
    plist.write_text("<plist/>")
    with patch("quota_monitor.cli.uninstall.uninstall_launch_agent") as remove:
        rc = uninstall(launch_agent_label="io.x", plist_path=plist)
    assert rc == 0
    remove.assert_called_once_with(plist_path=plist)


def test_uninstall_is_noop_when_plist_missing(tmp_path, capsys):
    plist = tmp_path / "no.plist"
    rc = uninstall(launch_agent_label="io.x", plist_path=plist)
    assert rc == 0
    out = capsys.readouterr().out + capsys.readouterr().err
    # The function should still print guidance about config/state.
    assert "config" in (out.lower() + "")
