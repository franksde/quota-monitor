from unittest.mock import MagicMock, patch
import pytest
from quota_monitor.notifiers import Alert, NotifierError
from quota_monitor.core.dispatch import dispatch_alert, DispatchOutcome


def _make_alert():
    return Alert(title="t", body="b", reset_at=1, source="claude")


def test_dispatch_uses_primary_when_it_succeeds():
    primary = MagicMock(name="primary")
    fallback = MagicMock(name="fallback")
    outcome = dispatch_alert(_make_alert(), primary=primary, fallback=fallback, retry_delays=())
    assert outcome == DispatchOutcome.PRIMARY_SUCCESS
    primary.send.assert_called_once()
    fallback.send.assert_not_called()


def test_dispatch_retries_primary_on_retryable_error():
    primary = MagicMock(name="primary")
    primary.send.side_effect = [NotifierError("x", retryable=True), NotifierError("x", retryable=True), None]
    outcome = dispatch_alert(_make_alert(), primary=primary, fallback=None, retry_delays=(0, 0))
    assert outcome == DispatchOutcome.PRIMARY_SUCCESS
    assert primary.send.call_count == 3


def test_dispatch_skips_retry_on_non_retryable_and_uses_fallback():
    primary = MagicMock(name="primary")
    primary.send.side_effect = NotifierError("auth", retryable=False)
    fallback = MagicMock(name="fallback")
    outcome = dispatch_alert(_make_alert(), primary=primary, fallback=fallback, retry_delays=(0, 0, 0))
    assert outcome == DispatchOutcome.FALLBACK_SUCCESS
    primary.send.assert_called_once()
    fallback.send.assert_called_once()


def test_dispatch_returns_total_failure_when_both_fail():
    primary = MagicMock(name="primary")
    primary.send.side_effect = NotifierError("x", retryable=False)
    fallback = MagicMock(name="fallback")
    fallback.send.side_effect = NotifierError("y", retryable=False)
    outcome = dispatch_alert(_make_alert(), primary=primary, fallback=fallback, retry_delays=())
    assert outcome == DispatchOutcome.TOTAL_FAILURE


def test_dispatch_returns_failure_when_no_fallback_and_primary_fails():
    primary = MagicMock(name="primary")
    primary.send.side_effect = NotifierError("x", retryable=False)
    outcome = dispatch_alert(_make_alert(), primary=primary, fallback=None, retry_delays=())
    assert outcome == DispatchOutcome.TOTAL_FAILURE
