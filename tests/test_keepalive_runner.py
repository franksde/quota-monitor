from pathlib import Path
from unittest.mock import patch, MagicMock

from quota_monitor.keepalive.runner import run_keepalive


def test_runner_invokes_claude_cli_with_phrase_and_model():
    with patch("quota_monitor.keepalive.runner.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stderr="")
        ok = run_keepalive(claude_cli="/opt/claude", shell="/bin/zsh", phrase="hello", model="haiku")
    assert ok is True
    cmd = run.call_args[0][0]
    assert "/bin/zsh" in cmd
    full = " ".join(cmd)
    assert "/opt/claude" in full
    assert "hello" in full
    assert "haiku" in full
    assert "--no-session-persistence" not in full
    assert "--setting-sources user" in full
    assert "--system-prompt 'Reply exactly OK.'" in full
    assert "--tools" in full
    assert "--disable-slash-commands" in full
    assert run.call_args.kwargs["cwd"] == Path.home()


def test_runner_returns_false_on_nonzero_exit():
    with patch("quota_monitor.keepalive.runner.subprocess.run") as run:
        run.return_value = MagicMock(returncode=1, stderr="boom")
        ok = run_keepalive(claude_cli="/opt/claude", shell="/bin/zsh", phrase="hi", model="haiku")
    assert ok is False


def test_runner_returns_false_on_timeout():
    import subprocess as sp
    with patch("quota_monitor.keepalive.runner.subprocess.run", side_effect=sp.TimeoutExpired(cmd="x", timeout=1)):
        ok = run_keepalive(claude_cli="/opt/claude", shell="/bin/zsh", phrase="hi", model="haiku")
    assert ok is False
