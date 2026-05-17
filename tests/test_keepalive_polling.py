from unittest.mock import patch
from quota_monitor.core.state import State
from quota_monitor.core.window import WINDOW_SECONDS
from quota_monitor.keepalive.polling import polling_tick, PollingDecision


def test_no_action_when_window_active_and_recent_activity():
    # 5 timestamps within last 30 min -> latest window's reset is in future, and is_idle False.
    now = 1_000_000.0
    ts = tuple(now - 60 * i for i in range(5))
    decision, _ = polling_tick(
        state=State(), now=now, timestamps=ts,
        idle_seconds=5 * 3600, claude_cli="/c", shell="/sh",
        model="haiku", phrase_pool=(),
    )
    assert decision is PollingDecision.SKIP


def test_no_action_when_raw_window_active_but_default_correction_would_expire():
    now = 10_000.0
    ts = (now - WINDOW_SECONDS + 100,)
    with patch("quota_monitor.keepalive.polling.run_keepalive") as run:
        decision, _ = polling_tick(
            state=State(), now=now, timestamps=ts,
            idle_seconds=5 * 3600, claude_cli="/c", shell="/sh",
            model="haiku", phrase_pool=("a",),
        )
    assert decision is PollingDecision.SKIP
    run.assert_not_called()


def test_fires_keepalive_when_no_history_at_all():
    state = State()
    with patch("quota_monitor.keepalive.polling.run_keepalive", return_value=True) as run:
        decision, new_state = polling_tick(
            state=state, now=1_000_000, timestamps=(),
            idle_seconds=5 * 3600, claude_cli="/c", shell="/sh",
            model="haiku", phrase_pool=("a",),
        )
    assert decision is PollingDecision.FIRED
    run.assert_called_once()
    assert new_state.keepalive.phrase_pool_size_at_init == 1


def test_fires_keepalive_when_latest_window_already_reset():
    # Latest window started long ago — its reset is in the past now.
    now = 1_000_000.0
    ts = (now - WINDOW_SECONDS - 100,)  # one stale activity outside any active window
    with patch("quota_monitor.keepalive.polling.run_keepalive", return_value=True):
        decision, _ = polling_tick(
            state=State(), now=now, timestamps=ts,
            idle_seconds=5 * 3600, claude_cli="/c", shell="/sh",
            model="haiku", phrase_pool=("a",),
        )
    assert decision is PollingDecision.FIRED


def test_fires_when_window_active_but_idle_threshold_exceeded():
    # Window opened recently but no activity in last `idle_seconds` -> still keepalive.
    now = 1_000_000.0
    ts = (now - 60 * 60,)  # 1h ago, only one activity, idle_seconds=5h means is_idle True
    with patch("quota_monitor.keepalive.polling.run_keepalive", return_value=True):
        decision, _ = polling_tick(
            state=State(), now=now, timestamps=ts,
            idle_seconds=30 * 60, claude_cli="/c", shell="/sh",   # idle threshold 30 min
            model="haiku", phrase_pool=("a",),
        )
    assert decision is PollingDecision.FIRED


def test_failure_does_not_mutate_phrase_state():
    state = State()
    with patch("quota_monitor.keepalive.polling.run_keepalive", return_value=False):
        decision, new_state = polling_tick(
            state=state, now=1_000_000, timestamps=(),
            idle_seconds=5 * 3600, claude_cli="/c", shell="/sh",
            model="haiku", phrase_pool=("a",),
        )
    assert decision is PollingDecision.FAILED
    assert new_state.keepalive == state.keepalive
