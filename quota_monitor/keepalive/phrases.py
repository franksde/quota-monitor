"""Phrase pool for keepalive content randomization.

The pool reduces content fingerprinting. It does NOT defeat pattern-based
detection (request timing, token volume, session shape). See README §Risks.
"""
import random
from dataclasses import dataclass
from typing import Callable, Sequence

DEFAULT_PHRASES: tuple[str, ...] = (
    "hi", "hello", "hey", "yo", "thanks",
    "morning", "你好", "嗨", "👋", "ok",
)


@dataclass(frozen=True)
class PhraseState:
    used_indices: tuple[int, ...] = ()
    size_at_init: int = 0


def pick_phrase(
    pool: Sequence[str],
    state: PhraseState,
    *,
    rng: Callable[[Sequence[int]], int] = random.choice,
) -> tuple[str, PhraseState]:
    """Pick a phrase with no-repeat semantics. Returns (phrase, new_state)."""
    if not pool:
        pool = DEFAULT_PHRASES
    pool_size = len(pool)
    # Reset if pool changed or all exhausted.
    used = state.used_indices
    if state.size_at_init != pool_size:
        used = ()
    if len(used) >= pool_size:
        used = ()
    available = [i for i in range(pool_size) if i not in used]
    chosen_idx = rng(available)
    phrase = pool[chosen_idx]
    return phrase, PhraseState(
        used_indices=tuple(sorted(used + (chosen_idx,))),
        size_at_init=pool_size,
    )
