# Adding a Notifier

## Protocol

```python
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

@dataclass(frozen=True)
class Alert:
    title: str
    body: str
    reset_at: int
    source: str

class Notifier(Protocol):
    name: str

    def send(self, alert: Alert) -> None:
        """Send the alert. Return None on success, raise NotifierError on failure."""
        ...
```

## Implement the Class

Create `quota_monitor/notifiers/<name>.py`:

```python
from . import Alert, NotifierError

class MyNotifier:
    name = "my_notifier"

    def send(self, alert: Alert) -> None:
        ...
```

Raise `NotifierError(message, retryable=True)` for transient failures and `retryable=False` for permanent configuration errors.

## Wire Runtime Selection

Update `quota_monitor/cli/run.py` in `_build_notifier()`:

```python
if name == "my_notifier":
    return MyNotifier(...)
```

Update `quota_monitor/cli/notify_test.py` so users can test it directly:

```python
elif name == "my_notifier":
    notifier = MyNotifier(...)
```

## Add Tests

Create `tests/test_notifier_<name>.py` following the Telegram pattern:

- Sends the expected payload.
- Converts network failures to `NotifierError`.
- Marks retryable and permanent errors correctly.
- Does not require real credentials or network.

## Add Setup Wizard Support

Update `quota_monitor/cli/setup.py` step 3:

- Add the notifier to the choices.
- Collect any required configuration or secrets.
- Render config in `_render_config()`.
- Render secrets in `_render_env()` if needed.

## Update Docs

Update both `README.md` and `README.zh-CN.md` with the new channel in "Choose your notification channel".
