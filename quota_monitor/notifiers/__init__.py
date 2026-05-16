from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Alert:
    title: str        # i18n-resolved
    body: str         # i18n-resolved, may include markdown
    reset_at: int     # epoch seconds; relays use this to schedule delivery
    source: str       # "claude" | "codex"


class NotifierError(Exception):
    """Raised by Notifier.send on failure. `retryable=True` for transient (network) issues."""

    def __init__(self, message: str, *, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


@runtime_checkable
class Notifier(Protocol):
    name: str

    def send(self, alert: Alert) -> None:
        """Send the alert. Return None on success, raise NotifierError on failure."""
        ...
