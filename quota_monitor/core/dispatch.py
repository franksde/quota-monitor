import enum
import sys
import time
from typing import Optional

from ..notifiers import Alert, Notifier, NotifierError

DEFAULT_RETRY_DELAYS = (1.0, 3.0, 9.0)


class DispatchOutcome(enum.Enum):
    PRIMARY_SUCCESS = "primary_success"
    FALLBACK_SUCCESS = "fallback_success"
    TOTAL_FAILURE = "total_failure"


def _try_send(notifier: Notifier, alert: Alert, retry_delays: tuple[float, ...]) -> bool:
    attempts = 1 + len(retry_delays)
    for i in range(attempts):
        try:
            notifier.send(alert)
            return True
        except NotifierError as e:
            print(f"[warn] {notifier.name} send failed: {e} (retryable={e.retryable})", file=sys.stderr)
            if not e.retryable or i == attempts - 1:
                return False
            time.sleep(retry_delays[i])
    return False


def dispatch_alert(
    alert: Alert,
    *,
    primary: Notifier,
    fallback: Optional[Notifier],
    retry_delays: tuple[float, ...] = DEFAULT_RETRY_DELAYS,
) -> DispatchOutcome:
    if _try_send(primary, alert, retry_delays):
        return DispatchOutcome.PRIMARY_SUCCESS
    if fallback is None:
        return DispatchOutcome.TOTAL_FAILURE
    if _try_send(fallback, alert, retry_delays=()):
        return DispatchOutcome.FALLBACK_SUCCESS
    return DispatchOutcome.TOTAL_FAILURE
