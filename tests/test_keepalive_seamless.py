from dataclasses import replace
from unittest.mock import patch
from quota_monitor.core.state import State, KeepaliveState
from quota_monitor.core.window import WINDOW_SECONDS
from quota_monitor.keepalive.seamless import seamless_tick, SeamlessDecision


def test_skip_no_window_when_no_timestamps():
    decision, _ = seamless_tick(
        state=State(), now=1000, timestamps=(),
        claude_cli="/c", shell="/sh", model="haiku", phrase_pool=(),
        trigger_minutes=30, buffer_seconds=60,
    )
    assert decision is SeamlessDecision.SKIP_NO_WINDOW


def test_skip_outside_when_far_from_reset():
    now = 1000.0
    ts = (now - 60,)   # 1 min ago -> latest window reset is now+5h-60s, far from trigger
    decision, _ = seamless_tick(
        state=State(), now=now, timestamps=ts,
        claude_cli="/c", shell="/sh", model="haiku", phrase_pool=(),
        trigger_minutes=30, buffer_seconds=60,
    )
    assert decision is SeamlessDecision.SKIP_OUTSIDE


def test_schedules_detached_subprocess_inside_trigger_window():
    # Latest window opens at (now - WINDOW_SECONDS + 500): reset is now + 500
    now = 10_000.0
    ts = (now - WINDOW_SECONDS + 500,)
    expected_reset = (now - WINDOW_SECONDS + 500) + WINDOW_SECONDS
    with patch("quota_monitor.keepalive.seamless.subprocess.Popen") as popen:
        decision, new_state = seamless_tick(
            state=State(), now=now, timestamps=ts,
            claude_cli="/c", shell="/sh", model="haiku", phrase_pool=("a",),
            trigger_minutes=30, buffer_seconds=60,
        )
    assert decision is SeamlessDecision.SCHEDULED
    cmd = popen.call_args[0][0]
    assert cmd[0] == "/sh"
    assert cmd[1] == "-lc"
    inner = cmd[2]
    assert "sleep " in inner   # detached sleep+exec, no tmux
    assert "/c -p" in inner
    assert "tmux" not in inner
    # Must be detached so the parent's exit doesn't kill the sleeping child
    assert popen.call_args.kwargs.get("start_new_session") is True
    assert new_state.keepalive.last_seamless_scheduled_for == int(expected_reset)


def test_skip_already_scheduled_for_same_reset():
    now = 10_000.0
    ts = (now - WINDOW_SECONDS + 500,)
    expected_reset = int((now - WINDOW_SECONDS + 500) + WINDOW_SECONDS)
    state = replace(State(), keepalive=KeepaliveState(last_seamless_scheduled_for=expected_reset))
    with patch("quota_monitor.keepalive.seamless.subprocess.Popen") as popen:
        decision, _ = seamless_tick(
            state=state, now=now, timestamps=ts,
            claude_cli="/c", shell="/sh", model="haiku", phrase_pool=("a",),
            trigger_minutes=30, buffer_seconds=60,
        )
    assert decision is SeamlessDecision.SKIP_ALREADY_SCHEDULED
    popen.assert_not_called()


def test_skip_expired_when_only_old_activity():
    # Only activity is from 2 full windows ago -> latest window reset is in the past.
    now = 100_000.0
    ts = (now - 2 * WINDOW_SECONDS,)
    decision, _ = seamless_tick(
        state=State(), now=now, timestamps=ts,
        claude_cli="/c", shell="/sh", model="haiku", phrase_pool=(),
        trigger_minutes=30, buffer_seconds=60,
    )
    assert decision is SeamlessDecision.SKIP_EXPIRED
