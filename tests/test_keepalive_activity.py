from quota_monitor.keepalive.activity import is_idle


def test_is_idle_true_when_no_recent_activity():
    assert is_idle(timestamps=(), now=1000.0, idle_seconds=3600) is True


def test_is_idle_false_when_recent_activity():
    assert is_idle(timestamps=(990.0,), now=1000.0, idle_seconds=3600) is False


def test_is_idle_true_when_all_activity_old():
    assert is_idle(timestamps=(100.0, 200.0), now=5000.0, idle_seconds=3600) is True


def test_is_idle_boundary_inclusive():
    # exactly idle_seconds ago should count as still recent
    assert is_idle(timestamps=(0.0,), now=3600.0, idle_seconds=3600) is False
