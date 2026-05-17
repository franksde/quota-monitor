from quota_monitor.core.state import State, ClaudeState, CodexState, default_state
from quota_monitor.core.window import (
    replay_windows, decide_alerts, AlertDecision, LatestWindow, WINDOW_SECONDS,
    RESET_CORRECTION_SECONDS,
)
from quota_monitor.probes import ProbeResult


# --- replay_windows: pure, takes no state ---

def test_empty_returns_none():
    assert replay_windows((), correction=0.0) is None


def test_single_timestamp_opens_first_window():
    w = replay_windows((1000.0,), correction=0.0)
    assert w == LatestWindow(start=1000.0, reset=1000.0 + WINDOW_SECONDS, count=1)


def test_clustered_timestamps_same_window():
    ts = (1000.0, 1001.0, 1002.0, 1003.0, 1004.0)
    w = replay_windows(ts, correction=0.0)
    assert w.start == 1000.0
    assert w.reset == 1000.0 + WINDOW_SECONDS
    assert w.count == 5


def test_returns_latest_window_when_history_spans_multiple_windows():
    base = 1000.0
    second_start = base + WINDOW_SECONDS + 1.0
    ts = (base, second_start, second_start + 10, second_start + 20)
    w = replay_windows(ts, correction=0.0)
    assert w.start == second_start
    assert w.reset == second_start + WINDOW_SECONDS
    assert w.count == 3


def test_replay_sorts_unordered_input():
    a = replay_windows((3.0, 1.0, 2.0), correction=0.0)
    b = replay_windows((1.0, 2.0, 3.0), correction=0.0)
    assert a == b


def test_three_consecutive_windows_returns_third():
    base = 1000.0
    w2 = base + WINDOW_SECONDS + 1
    w3 = w2 + WINDOW_SECONDS + 1
    ts = (base, w2, w3, w3 + 10, w3 + 20)
    w = replay_windows(ts, correction=0.0)
    assert w.start == w3
    assert w.count == 3


def test_default_correction_is_negative_300():
    assert RESET_CORRECTION_SECONDS == -300


def test_replay_windows_applies_default_correction():
    w = replay_windows((1000.0,))
    assert w.reset == 1000.0 + WINDOW_SECONDS + RESET_CORRECTION_SECONDS


def test_replay_windows_applies_custom_correction():
    w = replay_windows((1000.0,), correction=-120.0)
    assert w.reset == 1000.0 + WINDOW_SECONDS - 120.0


def test_replay_windows_correction_zero():
    w = replay_windows((1000.0,), correction=0.0)
    assert w.reset == 1000.0 + WINDOW_SECONDS


# --- regression: the original future-reset bug ---

def test_regression_future_reset_in_state_does_not_silence_alerts():
    """Original bug scenario: state has alerted_for_reset = future timestamp.
    Under Full Replay, state never feeds back into counting, so the algorithm
    happily computes the real latest window and triggers an alert.
    """
    now = 1000.0
    future = now + 120
    state = State(claude=ClaudeState(alerted_for_reset=int(future)))
    ts = (now - 3600, now - 1800, now - 1200, now - 600, now - 60)
    w = replay_windows(ts, correction=0.0)
    assert w is not None
    decisions = decide_alerts(
        state=state, claude_window=w, codex=None, now=now,
        claude_threshold=5, codex_threshold_percent=30,
    )
    assert len(decisions) == 1
    assert decisions[0].source == "claude"
    assert decisions[0].reset_at == int(w.reset)


# --- decide_alerts ---

def test_decide_emits_claude_alert_when_threshold_met():
    state = default_state()
    reset = 1000.0 + WINDOW_SECONDS + RESET_CORRECTION_SECONDS
    w = LatestWindow(start=1000.0, reset=reset, count=5)
    decisions = decide_alerts(
        state=state, claude_window=w, codex=None, now=1010.0,
        claude_threshold=5, codex_threshold_percent=30,
    )
    assert len(decisions) == 1
    assert decisions[0].source == "claude"
    assert decisions[0].reset_at == int(reset)


def test_decide_skips_when_below_threshold():
    state = default_state()
    reset = 1000.0 + WINDOW_SECONDS + RESET_CORRECTION_SECONDS
    w = LatestWindow(start=1000.0, reset=reset, count=3)
    decisions = decide_alerts(
        state=state, claude_window=w, codex=None, now=1010.0,
        claude_threshold=5, codex_threshold_percent=30,
    )
    assert decisions == []


def test_decide_suppresses_repeat_for_same_window():
    reset = 1000.0 + WINDOW_SECONDS + RESET_CORRECTION_SECONDS
    state = State(claude=ClaudeState(alerted_for_reset=int(reset)))
    w = LatestWindow(start=1000.0, reset=reset, count=6)
    decisions = decide_alerts(
        state=state, claude_window=w, codex=None, now=1010.0,
        claude_threshold=5, codex_threshold_percent=30,
    )
    assert decisions == []


def test_decide_skips_when_window_already_in_past():
    state = default_state()
    reset = 1.0 + WINDOW_SECONDS + RESET_CORRECTION_SECONDS
    w = LatestWindow(start=1.0, reset=reset, count=6)
    decisions = decide_alerts(
        state=state, claude_window=w, codex=None, now=reset + 10,
        claude_threshold=5, codex_threshold_percent=30,
    )
    assert decisions == []


def test_decide_emits_codex_alert_when_over_threshold():
    state = default_state()
    codex = ProbeResult(source="codex", timestamps=(), extra={"used_percent": 60, "reset_at": 99999})
    decisions = decide_alerts(
        state=state, claude_window=None, codex=codex, now=1.0,
        claude_threshold=5, codex_threshold_percent=30,
    )
    assert len(decisions) == 1
    assert decisions[0].source == "codex"
    assert decisions[0].reset_at == 99999


def test_decide_suppresses_codex_within_cooldown():
    state = State(codex=CodexState(cooldown_until=999999))
    codex = ProbeResult(source="codex", timestamps=(), extra={"used_percent": 60, "reset_at": 99999})
    decisions = decide_alerts(
        state=state, claude_window=None, codex=codex, now=1.0,
        claude_threshold=5, codex_threshold_percent=30,
    )
    assert decisions == []


def test_decide_suppresses_claude_within_cooldown_even_when_reset_drifted():
    """Regression: alert spam observed in the wild.

    LaunchAgent runs every 5 min. replay_windows is sensitive to scan-window
    boundary slide, so successive ticks can compute different reset_at values
    (seconds, minutes, occasionally hours apart). The previous dedupe key was
    `alerted_for_reset != int(window.reset)` — when reset_at drifts, this never
    matches, and the user gets one push per drift (observed: 5 pushes in 80 min).

    Fix: introduce a cooldown_until on ClaudeState (matching CodexState). After
    a successful alert we set cooldown ~4h forward, so re-fires for the same
    underlying window are dropped even when the noisy reset_at value moves.
    """
    state = State(claude=ClaudeState(
        alerted_for_reset=1000,   # previous alert was for some old reset_at
        cooldown_until=10_000,    # cooldown still active
    ))
    # current tick: reset_at completely different (algorithm drift) but within cooldown
    reset = 9_999.0
    w = LatestWindow(start=4999.0, reset=reset, count=10)
    decisions = decide_alerts(
        state=state, claude_window=w, codex=None, now=2_000,
        claude_threshold=5, codex_threshold_percent=30,
    )
    assert decisions == []


def test_decide_emits_claude_after_cooldown_expires():
    state = State(claude=ClaudeState(
        alerted_for_reset=1000,
        cooldown_until=2_000,  # cooldown over
    ))
    reset = 10_000.0
    w = LatestWindow(start=5000.0, reset=reset, count=10)
    decisions = decide_alerts(
        state=state, claude_window=w, codex=None, now=3_000,
        claude_threshold=5, codex_threshold_percent=30,
    )
    assert len(decisions) == 1


def test_claude_state_loads_legacy_without_cooldown(tmp_path):
    """Old state.json files don't have cooldown_until — must default to 0
    so users upgrading don't see a corruption warning."""
    import json
    from quota_monitor.core.state import load_state
    path = tmp_path / "state.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "claude": {"alerted_for_reset": 12345},
        "codex": {"alerted_for_reset": 0, "cooldown_until": 0},
        "keepalive": {"last_seamless_scheduled_for": 0, "phrase_pool_used_indices": [], "phrase_pool_size_at_init": 0},
    }))
    s = load_state(path)
    assert s.claude.alerted_for_reset == 12345
    assert s.claude.cooldown_until == 0
