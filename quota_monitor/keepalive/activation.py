"""Fire a minimal Claude call via tmux for post-reset window anchoring.

Used by run_once when it detects that a reset has passed and no local
JSONL activity exists in the new window. A single fire here makes Claude
Code write a new turn to the JSONL, which becomes the authoritative anchor
for downstream window math — no more "anchor + N*5h" mechanical rolling.

Fire-and-forget by design: a True return only confirms the tmux session
launched. Real success is checked on the next tick by re-scanning the
JSONL for a timestamp in the new window.
"""
import os
import random
import shlex
import shutil
import subprocess
import sys
import time
from typing import Optional, Sequence

from .phrases import PhraseState, pick_phrase


# Same fallback list as seamless used to keep — macOS LaunchAgent's PATH
# excludes Homebrew prefixes, so plain `shutil.which("tmux")` fails under
# launchd even when the binary is installed.
_TMUX_FALLBACK_PATHS = (
    "/opt/homebrew/bin/tmux",   # Apple Silicon brew
    "/usr/local/bin/tmux",      # Intel brew
    "/opt/local/bin/tmux",      # MacPorts
)


def _find_tmux() -> Optional[str]:
    p = shutil.which("tmux")
    if p:
        return p
    for candidate in _TMUX_FALLBACK_PATHS:
        if os.path.exists(candidate):
            return candidate
    return None


def fire_activation(
    *,
    claude_cli: str,
    shell: str,
    model: str,
    phrase_pool: Sequence[str],
    phrase_state: PhraseState,
    delay_seconds: int = 0,
) -> tuple[bool, PhraseState]:
    """Launch a minimal Claude call inside a detached tmux session.

    Args:
        claude_cli: path to the `claude` binary
        shell: login shell to wrap the call (so ~/.zprofile populates PATH
               and any cc-switch / provider env vars)
        model: passed to claude via --model
        phrase_pool: candidate input strings; empty falls back to
                     DEFAULT_PHRASES inside pick_phrase
        phrase_state: persisted no-repeat phrase tracking; advanced only
                      on tmux-launch success
        delay_seconds: if > 0, prefix the inner command with `sleep N &&`
                       so the call fires later. Default 0 = immediate fire.

    Returns:
        (ok, new_phrase_state). `ok` is True iff tmux returned exit 0.
        On any failure, phrase_state is returned unchanged so the next
        attempt doesn't burn a phrase.
    """
    tmux_bin = _find_tmux()
    if tmux_bin is None:
        print(
            "[error] keepalive needs tmux. Install: brew install tmux  (or apt/port equivalent)",
            file=sys.stderr,
        )
        return False, phrase_state

    phrase, new_phrase_state = pick_phrase(phrase_pool, phrase_state, rng=random.choice)
    quoted_phrase = shlex.quote(phrase)
    inner = (
        f"{shlex.quote(claude_cli)} -p {quoted_phrase} "
        f"--model {shlex.quote(model)} --no-session-persistence "
        f"--bare --system-prompt ping --tools '' --disable-slash-commands"
    )
    session_name = f"qm_keepalive_{time.time_ns()}"
    if delay_seconds > 0:
        cmd_str = f"sleep {delay_seconds} && {shell} -lc {shlex.quote(inner)}"
    else:
        cmd_str = f"{shell} -lc {shlex.quote(inner)}"
    tmux_cmd = [tmux_bin, "new-session", "-d", "-s", session_name, cmd_str]
    try:
        result = subprocess.run(tmux_cmd, capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"[error] tmux schedule failed: {e}", file=sys.stderr)
        return False, phrase_state
    if result.returncode != 0:
        print(f"[error] tmux returned {result.returncode}: {result.stderr.strip()}", file=sys.stderr)
        return False, phrase_state
    return True, new_phrase_state
