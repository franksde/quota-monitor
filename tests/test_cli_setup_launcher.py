"""Tests for stable launcher resolution in scheduled-task install.

Regression: pre-0.3.1 setup wrote `sys.executable -m quota_monitor` into the
LaunchAgent plist, which is a versioned Cellar path that disappears on
`brew upgrade`, leaving the LaunchAgent dead with EX_CONFIG (78) and no
keepalive ticks until manual reinstall.
"""
import plistlib
import sys
from unittest.mock import patch

from quota_monitor.cli.setup import _launcher_args, _install_launchagent


def test_launcher_args_prefers_console_script_on_path():
    with patch("quota_monitor.cli.setup.shutil.which",
               return_value="/opt/homebrew/bin/quota-monitor"):
        assert _launcher_args() == ["/opt/homebrew/bin/quota-monitor", "run"]


def test_launcher_args_falls_back_to_python_module_when_script_missing():
    with patch("quota_monitor.cli.setup.shutil.which", return_value=None):
        assert _launcher_args() == [sys.executable, "-m", "quota_monitor", "run"]


def test_install_launchagent_writes_stable_path_into_plist(tmp_path):
    """End-to-end: plist program is the console-script shim, not a versioned
    Cellar Python — survives brew upgrade."""
    captured = {}

    def fake_install(*, plist_path, plist_content):
        captured["path"] = plist_path
        captured["content"] = plist_content

    with patch("quota_monitor.cli.setup.shutil.which",
               return_value="/opt/homebrew/bin/quota-monitor"), \
         patch("quota_monitor.platform.schedule.install_launch_agent",
               side_effect=fake_install), \
         patch("quota_monitor.platform.paths.launch_agent_path",
               return_value=tmp_path / "agent.plist"):
        _install_launchagent(data_dir=tmp_path)

    parsed = plistlib.loads(captured["content"].encode())
    assert parsed["ProgramArguments"] == ["/opt/homebrew/bin/quota-monitor", "run"]
    # Defense in depth: ensure no Cellar-versioned path leaked through.
    assert "Cellar" not in captured["content"]
