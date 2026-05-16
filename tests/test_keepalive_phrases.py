from quota_monitor.keepalive.phrases import (
    DEFAULT_PHRASES, pick_phrase, PhraseState,
)


def test_default_pool_has_ten_phrases():
    assert len(DEFAULT_PHRASES) == 10
    assert len(set(DEFAULT_PHRASES)) == 10


def test_pick_returns_unused_phrase():
    pool = ("a", "b", "c")
    state = PhraseState(used_indices=(0, 1), size_at_init=3)
    phrase, new_state = pick_phrase(pool, state, rng=lambda seq: seq[0])
    assert phrase == "c"
    assert set(new_state.used_indices) == {0, 1, 2}


def test_pick_resets_when_pool_full():
    pool = ("a", "b")
    state = PhraseState(used_indices=(0, 1), size_at_init=2)
    phrase, new_state = pick_phrase(pool, state, rng=lambda seq: seq[0])
    # All exhausted -> reset before picking.
    assert phrase in pool
    assert len(new_state.used_indices) == 1


def test_pick_resets_when_pool_size_changes():
    state = PhraseState(used_indices=(0, 1, 2), size_at_init=3)
    pool = ("a", "b", "c", "d", "e")  # user added phrases
    phrase, new_state = pick_phrase(pool, state, rng=lambda seq: seq[0])
    assert phrase in pool
    assert new_state.size_at_init == 5
    assert len(new_state.used_indices) == 1


def test_uses_default_pool_when_user_pool_empty():
    state = PhraseState()
    phrase, new_state = pick_phrase((), state, rng=lambda seq: seq[0])
    assert phrase in DEFAULT_PHRASES
    assert new_state.size_at_init == len(DEFAULT_PHRASES)


def test_full_cycle_no_duplicates_within_pool():
    pool = ("a", "b", "c", "d", "e")
    state = PhraseState()
    seen = []
    rng = lambda seq: seq[0]  # deterministic
    for _ in range(len(pool)):
        phrase, state = pick_phrase(pool, state, rng=rng)
        seen.append(phrase)
    assert sorted(seen) == sorted(pool)
