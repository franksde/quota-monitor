from dataclasses import replace
from unittest.mock import MagicMock, patch

from quota_monitor.cli.run import _maybe_post_reset_activate
from quota_monitor.core.state import ClaudeState, State, default_state
from quota_monitor.core.window import WINDOW_SECONDS


def _cfg(max_attempts: int = 3, model: str = "haiku") -> MagicMock:
    cfg = MagicMock()
    cfg.keepalive.model = model
    cfg.keepalive.phrase_pool = ("hi",)
    cfg.keepalive.max_activation_attempts = max_attempts
    return cfg


def _fake_fire(ok: bool = True):
    """Returns a patch context for fire_activation returning (ok, unchanged_state)."""
    def _impl(*, phrase_state, **_):
        return (ok, phrase_state)
    return patch("quota_monitor.cli.run.fire_activation", side_effect=_impl)


def test_skip_when_anchor_in_future():
    """precise.reset > now means the current window hasn't ended yet — nothing
    to activate. State must not change."""
    cfg = _cfg()
    now = 10_000.0
    precise = MagicMock(five_hour_resets_at=now + 3600)
    claude_result = MagicMock(timestamps=())

    with _fake_fire() as fire:
        new_state = _maybe_post_reset_activate(
            cfg=cfg, state=default_state(), precise=precise,
            claude_result=claude_result, now=now, dry_run=False,
        )

    fire.assert_not_called()
    assert new_state == default_state()


def test_skip_when_no_anchor_available():
    cfg = _cfg()
    now = 10_000.0
    claude_result = MagicMock(timestamps=())

    with _fake_fire() as fire:
        new_state = _maybe_post_reset_activate(
            cfg=cfg, state=default_state(), precise=None,
            claude_result=claude_result, now=now, dry_run=False,
        )

    fire.assert_not_called()
    assert new_state == default_state()


def test_skip_and_clear_state_when_post_reset_activity_exists():
    """User (or previous keepalive) already produced a JSONL turn in the
    new window — nothing for us to do. Stale attempt state must be cleared."""
    cfg = _cfg()
    anchor = 10_000.0
    now = anchor + 600  # 10 min after reset
    claude_result = MagicMock(timestamps=(anchor + 60,))  # one turn after reset
    state = State(claude=ClaudeState(
        last_known_good_reset_at=anchor,
        keepalive_attempted_for_reset=int(anchor),
        keepalive_attempt_count=2,
    ))

    with _fake_fire() as fire:
        new_state = _maybe_post_reset_activate(
            cfg=cfg, state=state, precise=None,
            claude_result=claude_result, now=now, dry_run=False,
        )

    fire.assert_not_called()
    assert new_state.claude.keepalive_attempted_for_reset == 0
    assert new_state.claude.keepalive_attempt_count == 0


def test_fires_and_records_first_attempt():
    cfg = _cfg()
    anchor = 10_000.0
    now = anchor + 600
    claude_result = MagicMock(timestamps=())  # empty since reset
    state = State(claude=ClaudeState(last_known_good_reset_at=anchor))

    with _fake_fire() as fire:
        new_state = _maybe_post_reset_activate(
            cfg=cfg, state=state, precise=None,
            claude_result=claude_result, now=now, dry_run=False,
        )

    fire.assert_called_once()
    assert fire.call_args.kwargs["delay_seconds"] == 0
    assert new_state.claude.keepalive_attempted_for_reset == int(anchor)
    assert new_state.claude.keepalive_attempt_count == 1


def test_increments_attempt_count_on_same_reset():
    cfg = _cfg()
    anchor = 10_000.0
    now = anchor + 900
    claude_result = MagicMock(timestamps=())
    state = State(claude=ClaudeState(
        last_known_good_reset_at=anchor,
        keepalive_attempted_for_reset=int(anchor),
        keepalive_attempt_count=1,
    ))

    with _fake_fire() as fire:
        new_state = _maybe_post_reset_activate(
            cfg=cfg, state=state, precise=None,
            claude_result=claude_result, now=now, dry_run=False,
        )

    fire.assert_called_once()
    assert new_state.claude.keepalive_attempted_for_reset == int(anchor)
    assert new_state.claude.keepalive_attempt_count == 2


def test_gives_up_after_max_attempts():
    cfg = _cfg(max_attempts=3)
    anchor = 10_000.0
    now = anchor + 1500
    claude_result = MagicMock(timestamps=())
    state = State(claude=ClaudeState(
        last_known_good_reset_at=anchor,
        keepalive_attempted_for_reset=int(anchor),
        keepalive_attempt_count=3,
    ))

    with _fake_fire() as fire:
        new_state = _maybe_post_reset_activate(
            cfg=cfg, state=state, precise=None,
            claude_result=claude_result, now=now, dry_run=False,
        )

    fire.assert_not_called()
    # State preserved (we gave up; don't keep re-incrementing forever)
    assert new_state.claude.keepalive_attempted_for_reset == int(anchor)
    assert new_state.claude.keepalive_attempt_count == 3


def test_gives_up_state_clears_when_activity_finally_appears():
    """After 3 strikes we stopped firing; if the user comes back next day
    and starts using Claude, activity appears → clean the strike state."""
    cfg = _cfg(max_attempts=3)
    anchor = 10_000.0
    now = anchor + 1500
    claude_result = MagicMock(timestamps=(anchor + 100,))
    state = State(claude=ClaudeState(
        last_known_good_reset_at=anchor,
        keepalive_attempted_for_reset=int(anchor),
        keepalive_attempt_count=3,
    ))

    with _fake_fire() as fire:
        new_state = _maybe_post_reset_activate(
            cfg=cfg, state=state, precise=None,
            claude_result=claude_result, now=now, dry_run=False,
        )

    fire.assert_not_called()
    assert new_state.claude.keepalive_attempted_for_reset == 0
    assert new_state.claude.keepalive_attempt_count == 0


def test_resets_count_when_crossing_into_new_period():
    """Anchor 07:10, now 17:30 → most_recent_reset = 17:10 (not 12:10).
    Previously attempted 12:10 — switching to 17:10 starts fresh count."""
    cfg = _cfg()
    anchor = 10_000.0
    prior_reset = int(anchor + WINDOW_SECONDS)        # the 12:10-equivalent
    next_reset = int(anchor + 2 * WINDOW_SECONDS)     # the 17:10-equivalent
    now = next_reset + 600
    claude_result = MagicMock(timestamps=())
    state = State(claude=ClaudeState(
        last_known_good_reset_at=anchor,
        keepalive_attempted_for_reset=prior_reset,
        keepalive_attempt_count=2,
    ))

    with _fake_fire() as fire:
        new_state = _maybe_post_reset_activate(
            cfg=cfg, state=state, precise=None,
            claude_result=claude_result, now=now, dry_run=False,
        )

    fire.assert_called_once()
    assert new_state.claude.keepalive_attempted_for_reset == next_reset
    assert new_state.claude.keepalive_attempt_count == 1


def test_tmux_failure_still_bumps_count_to_avoid_infinite_loop():
    """If tmux can't launch (binary missing, sandbox denied), we still
    advance the count — otherwise every tick re-tries forever with no
    progress signal."""
    cfg = _cfg()
    anchor = 10_000.0
    now = anchor + 600
    claude_result = MagicMock(timestamps=())
    state = State(claude=ClaudeState(last_known_good_reset_at=anchor))

    with _fake_fire(ok=False) as fire:
        new_state = _maybe_post_reset_activate(
            cfg=cfg, state=state, precise=None,
            claude_result=claude_result, now=now, dry_run=False,
        )

    fire.assert_called_once()
    assert new_state.claude.keepalive_attempted_for_reset == int(anchor)
    assert new_state.claude.keepalive_attempt_count == 1


def test_dry_run_does_not_call_fire_but_still_advances_state():
    cfg = _cfg()
    anchor = 10_000.0
    now = anchor + 600
    claude_result = MagicMock(timestamps=())
    state = State(claude=ClaudeState(last_known_good_reset_at=anchor))

    with _fake_fire() as fire:
        new_state = _maybe_post_reset_activate(
            cfg=cfg, state=state, precise=None,
            claude_result=claude_result, now=now, dry_run=True,
        )

    fire.assert_not_called()
    assert new_state.claude.keepalive_attempted_for_reset == int(anchor)
    assert new_state.claude.keepalive_attempt_count == 1


def test_precise_anchor_takes_priority_over_last_known_good():
    """precise (HUD-fresh) is more current than last_known_good (state-cached).
    Use precise to compute most_recent_reset."""
    cfg = _cfg()
    last_known = 5_000.0
    precise_anchor = 10_000.0  # newer
    now = precise_anchor + 600
    precise = MagicMock(five_hour_resets_at=precise_anchor)
    claude_result = MagicMock(timestamps=())
    state = State(claude=ClaudeState(last_known_good_reset_at=last_known))

    with _fake_fire() as fire:
        new_state = _maybe_post_reset_activate(
            cfg=cfg, state=state, precise=precise,
            claude_result=claude_result, now=now, dry_run=False,
        )

    fire.assert_called_once()
    # most_recent_reset must derive from precise_anchor, not last_known
    assert new_state.claude.keepalive_attempted_for_reset == int(precise_anchor)


def test_walks_anchor_forward_when_now_is_multiple_periods_past():
    """Anchor 07:10, now 18:00. most_recent_reset must be 17:10
    (anchor + 2*5h), not 07:10 itself."""
    cfg = _cfg()
    anchor = 10_000.0
    now = anchor + 2 * WINDOW_SECONDS + 1800  # 30 min into the 3rd period
    expected_recent = int(anchor + 2 * WINDOW_SECONDS)
    claude_result = MagicMock(timestamps=())
    state = State(claude=ClaudeState(last_known_good_reset_at=anchor))

    with _fake_fire() as fire:
        new_state = _maybe_post_reset_activate(
            cfg=cfg, state=state, precise=None,
            claude_result=claude_result, now=now, dry_run=False,
        )

    fire.assert_called_once()
    assert new_state.claude.keepalive_attempted_for_reset == expected_recent
