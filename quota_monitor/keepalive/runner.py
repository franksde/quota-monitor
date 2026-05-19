import shlex
import subprocess
import sys
from pathlib import Path

_SYSTEM_PROMPT = "Reply exactly OK."


def run_keepalive(*, claude_cli: str, shell: str, phrase: str, model: str, timeout: int = 60) -> bool:
    """Invoke claude CLI to send a single keepalive message. Returns True on success."""
    quoted_phrase = shlex.quote(phrase)
    inner = (
        f"{shlex.quote(claude_cli)} -p {quoted_phrase} "
        f"--model {shlex.quote(model)} --setting-sources user "
        f"--system-prompt {shlex.quote(_SYSTEM_PROMPT)} "
        f"--tools '' --disable-slash-commands"
    )
    cmd = [shell, "-lc", inner]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=Path.home())
    except subprocess.TimeoutExpired:
        print(f"[error] keepalive timed out after {timeout}s", file=sys.stderr)
        return False
    except FileNotFoundError as e:
        print(f"[error] shell not found: {e}", file=sys.stderr)
        return False
    if result.returncode != 0:
        print(f"[error] keepalive failed (rc={result.returncode}): {result.stderr.strip()}", file=sys.stderr)
        return False
    return True
