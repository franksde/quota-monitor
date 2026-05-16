import enum
import random
from dataclasses import replace
from typing import Sequence

from ..core.state import State
from ..core.window import replay_windows
from ..i18n import t
from .activity import is_idle
from .phrases import PhraseState, pick_phrase
from .runner import run_keepalive


class PollingDecision(enum.Enum):
    SKIP = "skip"        # window active and recent activity present
    FIRED = "fired"      # keepalive successfully sent
    FAILED = "failed"    # attempted but subprocess returned non-zero


def polling_tick(
    *,
    state: State,
    now: float,
    timestamps: tuple[float, ...],
    idle_seconds: int,
    claude_cli: str,
    shell: str,
    model: str,
    phrase_pool: Sequence[str],
) -> tuple[PollingDecision, State]:
    window = replay_windows(timestamps)
    window_active = window is not None and now < window.reset
    if window_active and not is_idle(timestamps=timestamps, now=now, idle_seconds=idle_seconds):
        return PollingDecision.SKIP, state

    phrase_state = PhraseState(
        used_indices=state.keepalive.phrase_pool_used_indices,
        size_at_init=state.keepalive.phrase_pool_size_at_init,
    )
    phrase, new_phrase_state = pick_phrase(phrase_pool, phrase_state, rng=random.choice)
    ok = run_keepalive(claude_cli=claude_cli, shell=shell, phrase=phrase, model=model)
    if not ok:
        return PollingDecision.FAILED, state
    print(t("log.keepalive_fired", phrase=phrase))

    new_keepalive = replace(
        state.keepalive,
        phrase_pool_used_indices=new_phrase_state.used_indices,
        phrase_pool_size_at_init=new_phrase_state.size_at_init,
    )
    return PollingDecision.FIRED, replace(state, keepalive=new_keepalive)
