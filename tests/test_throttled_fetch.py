from quota_monitor.probes._throttled_fetch import (
    FetchHint,
    compute_dynamic_interval,
    should_skip_fetch,
)


def test_should_fetch_without_hint():
    assert should_skip_fetch(hint=None, threshold_percent=30, now=1_000.0) is False


def test_should_skip_when_threshold_reached_and_reset_is_future():
    hint = FetchHint(last_fetch_at=1_000, last_used_percent=30, last_reset_at=2_000)

    assert should_skip_fetch(hint=hint, threshold_percent=30, now=1_100.0) is True


def test_should_fetch_when_dynamic_interval_elapsed():
    hint = FetchHint(last_fetch_at=1_000, last_used_percent=5, last_reset_at=4_000)

    assert should_skip_fetch(hint=hint, threshold_percent=30, now=2_200.0) is False


def test_should_skip_when_dynamic_interval_not_elapsed():
    hint = FetchHint(last_fetch_at=1_000, last_used_percent=5, last_reset_at=4_000)

    assert should_skip_fetch(hint=hint, threshold_percent=30, now=2_199.0) is True


def test_should_fetch_when_reset_has_passed():
    hint = FetchHint(last_fetch_at=1_000, last_used_percent=30, last_reset_at=1_500)

    assert should_skip_fetch(hint=hint, threshold_percent=30, now=1_500.0) is False


def test_compute_dynamic_interval_uses_twenty_minutes_when_far_from_threshold():
    assert compute_dynamic_interval(used_percent=9, threshold_percent=30) == 20 * 60


def test_compute_dynamic_interval_uses_ten_minutes_when_mid_distance():
    assert compute_dynamic_interval(used_percent=20, threshold_percent=30) == 10 * 60


def test_compute_dynamic_interval_uses_base_when_close_to_threshold():
    assert compute_dynamic_interval(used_percent=29, threshold_percent=30) == 5 * 60
