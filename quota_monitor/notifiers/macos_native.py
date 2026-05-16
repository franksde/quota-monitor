import subprocess

from . import Alert, NotifierError


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


class MacOSNativeNotifier:
    name = "macos_native"

    def send(self, alert: Alert) -> None:
        title = _escape(alert.title)
        body = _escape(alert.body)
        script = f'display notification "{body}" with title "{title}"'
        try:
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        except subprocess.TimeoutExpired as e:
            raise NotifierError("osascript timed out", retryable=True) from e
        except FileNotFoundError as e:
            raise NotifierError("osascript not available (not macOS?)", retryable=False) from e
        if result.returncode != 0:
            raise NotifierError(f"osascript failed: {result.stderr.strip()}", retryable=False)
