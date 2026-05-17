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
    Never stores window start/reset — those come from Full Replay each tick.
    """
    alerted_for_reset: int = 0
    cooldown_until: int = 0


@dataclass(frozen=True)
class CodexState:
    alerted_for_reset: int = 0
    cooldown_until: int = 0
    last_fetch_at: int = 0
    last_used_percent: int = 0
    last_reset_at: int = 0


@dataclass(frozen=True)
class KeepaliveState:
    last_seamless_scheduled_for: int = 0
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
                        if k in {"alerted_for_reset", "cooldown_until"}}
        codex_block = {k: v for k, v in (raw.get("codex") or {}).items()
                       if k in {
                           "alerted_for_reset",
                           "cooldown_until",
                           "last_fetch_at",
                           "last_used_percent",
                           "last_reset_at",
                       }}
        return State(
            schema_version=raw.get("schema_version", SCHEMA_VERSION),
            claude=ClaudeState(**claude_block),
            codex=CodexState(**codex_block),
            keepalive=KeepaliveState(
                last_seamless_scheduled_for=(raw.get("keepalive") or {}).get("last_seamless_scheduled_for", 0),
                phrase_pool_used_indices=tuple((raw.get("keepalive") or {}).get("phrase_pool_used_indices", [])),
                phrase_pool_size_at_init=(raw.get("keepalive") or {}).get("phrase_pool_size_at_init", 0),
            ),
        )
    except TypeError as e:
        print(f"[warn] state schema mismatch ({e}); resetting to defaults", file=sys.stderr)
        return default_state()


def save_state(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = asdict(state)
    # Convert tuples (json doesn't preserve type but lists are fine on load).
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)
