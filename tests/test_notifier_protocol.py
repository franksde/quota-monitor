from quota_monitor.notifiers import Alert, Notifier, NotifierError


def test_alert_dataclass_shape():
    a = Alert(title="t", body="b", reset_at=100, source="claude")
    assert a.title == "t"
    assert a.source == "claude"


def test_notifier_error_carries_retryable_flag():
    e = NotifierError("x", retryable=True)
    assert e.retryable is True
    e2 = NotifierError("x", retryable=False)
    assert e2.retryable is False


def test_dummy_notifier_implements_protocol():
    class Dummy:
        name = "dummy"
        def send(self, alert: Alert) -> None:
            return None

    n: Notifier = Dummy()
    n.send(Alert(title="t", body="b", reset_at=1, source="claude"))
