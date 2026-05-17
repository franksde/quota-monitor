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


def test_schedules_tmux_inside_trigger_window():
    now = 10_000.0
    ts = (now - WINDOW_SECONDS + 500,)
    expected_reset = (now - WINDOW_SECONDS + 500) + WINDOW_SECONDS
    with patch("quota_monitor.keepalive.seamless._find_tmux", return_value="/opt/homebrew/bin/tmux"), \
         patch("quota_monitor.keepalive.seamless.subprocess.run") as run:
        run.return_value.returncode = 0
        decision, new_state = seamless_tick(
            state=State(), now=now, timestamps=ts,
            claude_cli="/c", shell="/sh", model="haiku", phrase_pool=("a",),
            trigger_minutes=30, buffer_seconds=60,
        )
    assert decision is SeamlessDecision.SCHEDULED
    cmd = run.call_args[0][0]
    # Absolute path, not bare "tmux" — LaunchAgent's PATH won't find brew tmux
    assert cmd[0] == "/opt/homebrew/bin/tmux"
    assert cmd[1] == "new-session"
    # The `sleep && claude ...` payload includes the minimal-context flags
    payload = cmd[-1]
    assert "sleep " in payload
    assert "/c -p" in payload
    assert "--bare" in payload
    assert "--system-prompt ping" in payload
    # --tools '' inside the inner cmd gets re-escaped by shlex.quote when the
    # whole inner is wrapped for `/sh -lc`. Just confirm the flag was passed.
    assert "--tools" in payload
    assert "--disable-slash-commands" in payload
    # Login shell so ~/.zprofile populates PATH and cc-switch / third-party env
    assert "/sh -lc" in payload
    assert new_state.keepalive.last_seamless_scheduled_for == int(expected_reset)


def test_fails_loudly_when_tmux_not_installed():
    now = 10_000.0
    ts = (now - WINDOW_SECONDS + 500,)
    with patch("quota_monitor.keepalive.seamless._find_tmux", return_value=None), \
         patch("quota_monitor.keepalive.seamless.subprocess.run") as run:
        decision, new_state = seamless_tick(
            state=State(), now=now, timestamps=ts,
            claude_cli="/c", shell="/sh", model="haiku", phrase_pool=("a",),
            trigger_minutes=30, buffer_seconds=60,
        )
    assert decision is SeamlessDecision.FAILED_NO_TMUX
    run.assert_not_called()
    # Don't burn the "already scheduled" slot — keep last_seamless_scheduled_for at 0
    # so the next tick can retry (e.g. after user installs tmux).
    assert new_state.keepalive.last_seamless_scheduled_for == 0


def test_skip_already_scheduled_for_same_reset():
    now = 10_000.0
    ts = (now - WINDOW_SECONDS + 500,)
    expected_reset = int((now - WINDOW_SECONDS + 500) + WINDOW_SECONDS)
    state = replace(State(), keepalive=KeepaliveState(last_seamless_scheduled_for=expected_reset))
    with patch("quota_monitor.keepalive.seamless._find_tmux", return_value="/opt/homebrew/bin/tmux"), \
         patch("quota_monitor.keepalive.seamless.subprocess.run") as run:
        decision, _ = seamless_tick(
            state=state, now=now, timestamps=ts,
            claude_cli="/c", shell="/sh", model="haiku", phrase_pool=("a",),
            trigger_minutes=30, buffer_seconds=60,
        )
    assert decision is SeamlessDecision.SKIP_ALREADY_SCHEDULED
    run.assert_not_called()


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
