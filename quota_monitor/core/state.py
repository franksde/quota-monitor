import fcntl
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ClaudeState:
    """Minimal: tracks which reset point has been alerted, and a cooldown so
    that a noisy reset_at value (replay_windows is sensitive to scan-window
    boundary slide) can't trigger repeat pushes for the same underlying window.
    last_known_good_reset_at is only populated from precise/HUD data; replay
    estimates never feed it.
    """
    alerted_for_reset: int = 0
    cooldown_until: int = 0
    last_known_good_reset_at: float = 0.0
    # CF Queue mode dedupe: which future reset we've already scheduled a
    # delayed "recovered" notification for. Prevents every LaunchAgent tick
    # from re-scheduling the same future alert.
    scheduled_alert_reset_at: int = 0
    # Post-reset activation: which past-reset epoch the keepalive subsystem
    # is currently trying to anchor (by injecting one minimal Claude call so
    # the local JSONL gets a new-window timestamp). Pair with attempt_count
    # for a 3-strike retry budget. Cleared once activity appears in the
    # window or when we give up.
    keepalive_attempted_for_reset: int = 0
    keepalive_attempt_count: int = 0


@dataclass(frozen=True)
class CodexState:
    alerted_for_reset: int = 0
    cooldown_until: int = 0
    last_fetch_at: int = 0
    last_used_percent: int = 0
    last_reset_at: int = 0
    scheduled_alert_reset_at: int = 0


@dataclass(frozen=True)
class KeepaliveState:
    phrase_pool_used_indices: tuple[int, ...] = ()
    phrase_pool_size_at_init: int = 0


@dataclass(frozen=True)
class State:
    schema_version: int = SCHEMA_VERSION
    claude: ClaudeState = field(default_factory=ClaudeState)
    codex: CodexState = field(default_factory=CodexState)
    keepalive: KeepaliveState = field(default_factory=KeepaliveState)


def default_state() -> State:
    return State()


def load_state(path: Path) -> State:
    if not path.exists():
        return default_state()
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"[warn] state file corrupted ({e}); resetting to defaults", file=sys.stderr)
        return default_state()

    try:
        # Backward-compatibility: silently ignore obsolete ClaudeState fields
        # (current_window_start / current_window_reset) that may exist in older state files.
        claude_block = {k: v for k, v in (raw.get("claude") or {}).items()
                        if k in {
                            "alerted_for_reset",
                            "cooldown_until",
                            "last_known_good_reset_at",
                            "scheduled_alert_reset_at",
                            "keepalive_attempted_for_reset",
                            "keepalive_attempt_count",
                        }}
        codex_block = {k: v for k, v in (raw.get("codex") or {}).items()
                       if k in {
                           "alerted_for_reset",
                           "cooldown_until",
                           "last_fetch_at",
                           "last_used_percent",
                           "last_reset_at",
                           "scheduled_alert_reset_at",
                       }}
        return State(
            schema_version=raw.get("schema_version", SCHEMA_VERSION),
            claude=ClaudeState(**claude_block),
            codex=CodexState(**codex_block),
            keepalive=KeepaliveState(
                # last_seamless_scheduled_for from older state files is
                # silently dropped — the seamless scheduling subsystem was
                # removed in 0.3.0, replaced by post-reset activation
                # (tracked on ClaudeState.keepalive_*).
                phrase_pool_used_indices=tuple((raw.get("keepalive") or {}).get("phrase_pool_used_indices", [])),
                phrase_pool_size_at_init=(raw.get("keepalive") or {}).get("phrase_pool_size_at_init", 0),
            ),
        )
    except TypeError as e:
        print(f"[warn] state schema mismatch ({e}); resetting to defaults", file=sys.stderr)
        return default_state()


def save_state(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(state)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            tmp = path.with_suffix(path.suffix + ".tmp")
            # Convert tuples (json doesn't preserve type but lists are fine on load).
            tmp.write_text(json.dumps(payload, indent=2))
            os.replace(tmp, path)
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
