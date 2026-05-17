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


# --- known_reset_at takes precedence over replay_windows estimate ---

def test_uses_known_reset_when_provided_and_in_future(tmp_path):
    """precise/HUD anchor cached in state.claude.last_known_good_reset_at
    must beat the noisy replay estimate. Regression: without this, a 5h
    window with continuous-but-shifted activity made seamless_tick fire
    keepalive ~2.5h early because estimated reset drifted left."""
    now = 10_000.0
    # estimated would compute reset = (now - WINDOW_SECONDS + 500) + WINDOW_SECONDS = now + 500
    # so trigger-minutes window check passes either way; we need the
    # delay calc + scheduled_for value to use known_reset, not estimated.
    ts = (now - WINDOW_SECONDS + 500,)
    estimated_reset = (now - WINDOW_SECONDS + 500) + WINDOW_SECONDS  # = now + 500
    known_reset = now + 800   # 5 min later than estimate; still within trigger window

    with patch("quota_monitor.keepalive.seamless._find_tmux", return_value="/opt/homebrew/bin/tmux"), \
         patch("quota_monitor.keepalive.seamless.subprocess.run") as run:
        run.return_value.returncode = 0
        decision, new_state = seamless_tick(
            state=State(), now=now, timestamps=ts,
            claude_cli="/c", shell="/sh", model="haiku", phrase_pool=("a",),
            trigger_minutes=30, buffer_seconds=60,
            known_reset_at=known_reset,
        )
    assert decision is SeamlessDecision.SCHEDULED
    # scheduled_for must be the known reset, not the estimate
    assert new_state.keepalive.last_seamless_scheduled_for == int(known_reset)
    # tmux sleep arg derived from known_reset, not estimated_reset
    payload = run.call_args[0][0][-1]
    expected_delay = int(known_reset - now) + 60  # buffer_seconds
    assert f"sleep {expected_delay} " in payload


def test_falls_back_to_estimate_when_known_reset_is_none():
    now = 10_000.0
    ts = (now - WINDOW_SECONDS + 500,)
    with patch("quota_monitor.keepalive.seamless._find_tmux", return_value="/opt/homebrew/bin/tmux"), \
         patch("quota_monitor.keepalive.seamless.subprocess.run") as run:
        run.return_value.returncode = 0
        decision, new_state = seamless_tick(
            state=State(), now=now, timestamps=ts,
            claude_cli="/c", shell="/sh", model="haiku", phrase_pool=("a",),
            trigger_minutes=30, buffer_seconds=60,
            known_reset_at=None,
        )
    assert decision is SeamlessDecision.SCHEDULED
    # falls back to estimated reset
    estimated_reset = (now - WINDOW_SECONDS + 500) + WINDOW_SECONDS
    assert new_state.keepalive.last_seamless_scheduled_for == int(estimated_reset)


def test_falls_back_to_estimate_when_known_reset_is_in_past():
    """Stale anchor from a previous window — don't trust it."""
    now = 10_000.0
    ts = (now - WINDOW_SECONDS + 500,)
    stale_known = now - 100  # in the past
    with patch("quota_monitor.keepalive.seamless._find_tmux", return_value="/opt/homebrew/bin/tmux"), \
         patch("quota_monitor.keepalive.seamless.subprocess.run") as run:
        run.return_value.returncode = 0
        decision, new_state = seamless_tick(
            state=State(), now=now, timestamps=ts,
            claude_cli="/c", shell="/sh", model="haiku", phrase_pool=("a",),
            trigger_minutes=30, buffer_seconds=60,
            known_reset_at=stale_known,
        )
    assert decision is SeamlessDecision.SCHEDULED
    estimated_reset = (now - WINDOW_SECONDS + 500) + WINDOW_SECONDS
    assert new_state.keepalive.last_seamless_scheduled_for == int(estimated_reset)


def test_falls_back_to_estimate_when_known_reset_too_far_in_future():
    """Anchor more than one full window away — almost certainly stale
    (e.g. last_known_good_reset_at was set, then user idled past 2 resets
    without any new precise data). Drop back to current local replay."""
    now = 10_000.0
    ts = (now - WINDOW_SECONDS + 500,)
    far_known = now + 2 * WINDOW_SECONDS  # 10 hours from now
    with patch("quota_monitor.keepalive.seamless._find_tmux", return_value="/opt/homebrew/bin/tmux"), \
         patch("quota_monitor.keepalive.seamless.subprocess.run") as run:
        run.return_value.returncode = 0
        decision, new_state = seamless_tick(
            state=State(), now=now, timestamps=ts,
            claude_cli="/c", shell="/sh", model="haiku", phrase_pool=("a",),
            trigger_minutes=30, buffer_seconds=60,
            known_reset_at=far_known,
        )
    assert decision is SeamlessDecision.SCHEDULED
    estimated_reset = (now - WINDOW_SECONDS + 500) + WINDOW_SECONDS
    assert new_state.keepalive.last_seamless_scheduled_for == int(estimated_reset)
