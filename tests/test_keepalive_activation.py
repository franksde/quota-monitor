from unittest.mock import patch
from quota_monitor.keepalive.activation import fire_activation
from quota_monitor.keepalive.phrases import PhraseState, DEFAULT_PHRASES


def _phrase_state() -> PhraseState:
    return PhraseState()


def test_fires_tmux_with_zero_delay_when_no_delay_specified():
    with patch("quota_monitor.keepalive.activation._find_tmux", return_value="/opt/homebrew/bin/tmux"), \
         patch("quota_monitor.keepalive.activation.subprocess.run") as run:
        run.return_value.returncode = 0
        ok, _ = fire_activation(
            claude_cli="/c", shell="/sh", model="haiku",
            phrase_pool=("hi",), phrase_state=_phrase_state(),
            delay_seconds=0,
        )
    assert ok is True
    cmd = run.call_args[0][0]
    assert cmd[0] == "/opt/homebrew/bin/tmux"
    assert cmd[1] == "new-session"
    payload = cmd[-1]
    # No `sleep N &&` prefix when delay=0
    assert "sleep " not in payload
    # Minimal-context claude flags still present, but the session must persist
    # so the next monitor tick can see the JSONL activity.
    assert "/c -p" in payload
    assert "--no-session-persistence" not in payload
    assert "--bare" not in payload
    assert "--setting-sources user" in payload
    assert "--system-prompt ping" in payload
    assert "--tools" in payload
    assert "--disable-slash-commands" in payload
    assert payload.startswith("cd ")
    assert "/sh -lc" in payload


def test_includes_sleep_prefix_when_delay_positive():
    with patch("quota_monitor.keepalive.activation._find_tmux", return_value="/opt/homebrew/bin/tmux"), \
         patch("quota_monitor.keepalive.activation.subprocess.run") as run:
        run.return_value.returncode = 0
        ok, _ = fire_activation(
            claude_cli="/c", shell="/sh", model="haiku",
            phrase_pool=("hi",), phrase_state=_phrase_state(),
            delay_seconds=60,
        )
    assert ok is True
    payload = run.call_args[0][0][-1]
    assert payload.startswith("sleep 60 && ")


def test_returns_false_when_tmux_missing():
    with patch("quota_monitor.keepalive.activation._find_tmux", return_value=None), \
         patch("quota_monitor.keepalive.activation.subprocess.run") as run:
        ok, new_state = fire_activation(
            claude_cli="/c", shell="/sh", model="haiku",
            phrase_pool=("hi",), phrase_state=_phrase_state(),
            delay_seconds=0,
        )
    assert ok is False
    # phrase state unchanged on failure (no consumption)
    assert new_state == _phrase_state()
    run.assert_not_called()


def test_returns_false_when_tmux_nonzero_exit():
    with patch("quota_monitor.keepalive.activation._find_tmux", return_value="/opt/homebrew/bin/tmux"), \
         patch("quota_monitor.keepalive.activation.subprocess.run") as run:
        run.return_value.returncode = 1
        run.return_value.stderr = "boom"
        ok, new_state = fire_activation(
            claude_cli="/c", shell="/sh", model="haiku",
            phrase_pool=("hi",), phrase_state=_phrase_state(),
            delay_seconds=0,
        )
    assert ok is False
    assert new_state == _phrase_state()


def test_empty_phrase_pool_uses_default_phrases():
    """Frank's prod config has phrase_pool=[]; the call must still work
    via pick_phrase's DEFAULT_PHRASES fallback."""
    with patch("quota_monitor.keepalive.activation._find_tmux", return_value="/opt/homebrew/bin/tmux"), \
         patch("quota_monitor.keepalive.activation.subprocess.run") as run:
        run.return_value.returncode = 0
        ok, _ = fire_activation(
            claude_cli="/c", shell="/sh", model="haiku",
            phrase_pool=(), phrase_state=_phrase_state(),
            delay_seconds=0,
        )
    assert ok is True
    payload = run.call_args[0][0][-1]
    # one of the default phrases must appear in the -p arg
    assert any(p in payload for p in DEFAULT_PHRASES)


def test_session_names_are_unique_across_calls():
    with patch("quota_monitor.keepalive.activation._find_tmux", return_value="/opt/homebrew/bin/tmux"), \
         patch("quota_monitor.keepalive.activation.subprocess.run") as run, \
         patch("quota_monitor.keepalive.activation.time.time_ns",
               side_effect=[111_000_000_001, 111_000_000_002]):
        run.return_value.returncode = 0
        for _ in range(2):
            fire_activation(
                claude_cli="/c", shell="/sh", model="haiku",
                phrase_pool=("hi",), phrase_state=_phrase_state(),
                delay_seconds=0,
            )
    session_names = [call.args[0][4] for call in run.call_args_list]
    assert session_names[0] != session_names[1]


def test_phrase_state_advances_on_success():
    with patch("quota_monitor.keepalive.activation._find_tmux", return_value="/opt/homebrew/bin/tmux"), \
         patch("quota_monitor.keepalive.activation.subprocess.run") as run:
        run.return_value.returncode = 0
        _, new_state = fire_activation(
            claude_cli="/c", shell="/sh", model="haiku",
            phrase_pool=("a", "b", "c"), phrase_state=_phrase_state(),
            delay_seconds=0,
        )
    assert new_state.size_at_init == 3
    assert len(new_state.used_indices) == 1
