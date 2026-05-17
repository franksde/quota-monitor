import plistlib
from pathlib import Path
from unittest.mock import patch, MagicMock
from quota_monitor.platform.schedule import (
    generate_launch_agent_plist, install_launch_agent, uninstall_launch_agent,
)


def test_plist_contains_label_program_and_interval(tmp_path):
    plist = generate_launch_agent_plist(
        label="io.github.frank.qm",
        program_arguments=["/usr/bin/python3.11", "-m", "quota_monitor", "run"],
        interval_seconds=300,
        stdout_log=tmp_path / "out.log",
        stderr_log=tmp_path / "err.log",
    )
    assert "<key>Label</key>" in plist
    assert "<string>io.github.frank.qm</string>" in plist
    assert "<key>ProgramArguments</key>" in plist
    assert "<string>/usr/bin/python3.11</string>" in plist
    assert "<key>StartInterval</key>" in plist
    assert "<integer>300</integer>" in plist
    assert "<key>RunAtLoad</key>" in plist
    assert "<true/>" in plist


def test_plist_sets_path_to_include_homebrew_and_macports(tmp_path):
    """LaunchAgent's default PATH excludes brew/macports, so plain `tmux` or
    `claude` lookups fail. plist must set PATH explicitly."""
    plist = generate_launch_agent_plist(
        label="x", program_arguments=["/p"], interval_seconds=300,
        stdout_log=tmp_path / "o", stderr_log=tmp_path / "e",
    )
    parsed = plistlib.loads(plist.encode())
    path = parsed["EnvironmentVariables"]["PATH"]
    assert "/opt/homebrew/bin" in path     # Apple Silicon brew
    assert "/usr/local/bin" in path        # Intel brew
    assert "/usr/bin" in path              # system fallback


def test_plist_escapes_xml_special_characters(tmp_path):
    plist = generate_launch_agent_plist(
        label="io.github.frank.qm&dev",
        program_arguments=["/tmp/a&b<runner>", "quota_monitor"],
        interval_seconds=300,
        stdout_log=tmp_path / "out&dev.log",
        stderr_log=tmp_path / "err<dev>.log",
    )
    parsed = plistlib.loads(plist.encode())
    assert parsed["Label"] == "io.github.frank.qm&dev"
    assert parsed["ProgramArguments"][0] == "/tmp/a&b<runner>"
    assert parsed["StandardOutPath"].endswith("out&dev.log")
    assert parsed["StandardErrorPath"].endswith("err<dev>.log")


def test_install_writes_file_and_calls_launchctl(tmp_path):
    plist_path = tmp_path / "agent.plist"
    with patch("quota_monitor.platform.schedule.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stderr="")
        install_launch_agent(plist_path=plist_path, plist_content="<plist/>")
    assert plist_path.read_text() == "<plist/>"
    run.assert_called_once()
    cmd = run.call_args[0][0]
    assert cmd[0] == "launchctl"
    assert "load" in cmd


def test_install_unloads_existing_launch_agent_before_replacing_plist(tmp_path):
    plist_path = tmp_path / "agent.plist"
    plist_path.write_text("<old/>")

    with patch("quota_monitor.platform.schedule.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stderr="")
        install_launch_agent(plist_path=plist_path, plist_content="<new/>")

    assert plist_path.read_text() == "<new/>"
    calls = [call.args[0] for call in run.call_args_list]
    assert calls[0] == ["launchctl", "unload", str(plist_path)]
    assert calls[1] == ["launchctl", "load", "-w", str(plist_path)]


def test_uninstall_calls_launchctl_unload_and_removes_file(tmp_path):
    plist_path = tmp_path / "agent.plist"
    plist_path.write_text("<plist/>")
    with patch("quota_monitor.platform.schedule.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stderr="")
        uninstall_launch_agent(plist_path=plist_path)
    assert not plist_path.exists()
    run.assert_called_once()
    cmd = run.call_args[0][0]
    assert "unload" in cmd
