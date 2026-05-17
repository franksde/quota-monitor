import enum
import random
import shlex
import subprocess
import sys
import time
from dataclasses import replace
from typing import Sequence

from ..core.state import State
from ..core.window import replay_windows
from .phrases import PhraseState, pick_phrase


class SeamlessDecision(enum.Enum):
    SKIP_NO_WINDOW = "skip_no_window"           # no activity -> no window to chase
    SKIP_OUTSIDE = "skip_outside"               # > trigger minutes left
    SKIP_EXPIRED = "skip_expired"               # window already reset
    SKIP_ALREADY_SCHEDULED = "skip_scheduled"   # already scheduled this reset
    SCHEDULED = "scheduled"                     # tmux scheduled successfully
    FAILED = "failed"                           # tmux invocation failed


def seamless_tick(
    *,
    state: State,
    now: float,
    timestamps: tuple[float, ...],
    claude_cli: str,
    shell: str,
    model: str,
    phrase_pool: Sequence[str],
    trigger_minutes: int,
    buffer_seconds: int,
) -> tuple[SeamlessDecision, State]:
    window = replay_windows(timestamps, correction=0.0)
    if window is None:
        return SeamlessDecision.SKIP_NO_WINDOW, state
    time_to_reset = window.reset - now
    if time_to_reset <= 0:
        return SeamlessDecision.SKIP_EXPIRED, state
    if time_to_reset > trigger_minutes * 60:
        return SeamlessDecision.SKIP_OUTSIDE, state
    if state.keepalive.last_seamless_scheduled_for == int(window.reset):
        return SeamlessDecision.SKIP_ALREADY_SCHEDULED, state

    phrase_state = PhraseState(
        used_indices=state.keepalive.phrase_pool_used_indices,
        size_at_init=state.keepalive.phrase_pool_size_at_init,
    )
    phrase, new_phrase_state = pick_phrase(phrase_pool, phrase_state, rng=random.choice)

    delay = int(time_to_reset) + buffer_seconds
    quoted_phrase = shlex.quote(phrase)
    inner = (
        f"{shlex.quote(claude_cli)} -p {quoted_phrase} "
        f"--model {shlex.quote(model)} --no-session-persistence"
    )
    session_name = f"qm_keepalive_{int(time.time())}"
    tmux_cmd = ["tmux", "new-session", "-d", "-s", session_name,
                f"sleep {delay} && {shell} -lc {shlex.quote(inner)}"]
    try:
        result = subprocess.run(tmux_cmd, capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"[error] tmux schedule failed: {e}", file=sys.stderr)
        return SeamlessDecision.FAILED, state
    if result.returncode != 0:
        print(f"[error] tmux returned {result.returncode}: {result.stderr.strip()}", file=sys.stderr)
        return SeamlessDecision.FAILED, state

    new_keepalive = replace(
        state.keepalive,
        last_seamless_scheduled_for=int(window.reset),
        phrase_pool_used_indices=new_phrase_state.used_indices,
        phrase_pool_size_at_init=new_phrase_state.size_at_init,
    )
    return SeamlessDecision.SCHEDULED, replace(state, keepalive=new_keepalive)
