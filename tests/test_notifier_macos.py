from unittest.mock import patch, MagicMock
import pytest
from quota_monitor.notifiers import Alert, NotifierError
from quota_monitor.notifiers.macos_native import MacOSNativeNotifier


def test_send_invokes_osascript():
    notifier = MacOSNativeNotifier()
    with patch("quota_monitor.notifiers.macos_native.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stderr="")
        notifier.send(Alert(title="t", body="b", reset_at=1, source="claude"))
    cmd = run.call_args[0][0]
    assert cmd[0] == "osascript"
    assert "-e" in cmd


def test_send_raises_non_retryable_on_nonzero_exit():
    notifier = MacOSNativeNotifier()
    with patch("quota_monitor.notifiers.macos_native.subprocess.run") as run:
        run.return_value = MagicMock(returncode=1, stderr="boom")
        with pytest.raises(NotifierError) as exc:
            notifier.send(Alert(title="t", body="b", reset_at=1, source="claude"))
    assert exc.value.retryable is False


def test_escapes_quotes_in_body():
    notifier = MacOSNativeNotifier()
    with patch("quota_monitor.notifiers.macos_native.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stderr="")
        notifier.send(Alert(title='ti"tle', body="bo\\dy", reset_at=1, source="claude"))
    script = run.call_args[0][0][-1]
    assert "\\\"" in script or '\\"' in script
