import shlex
import subprocess
import sys


def run_keepalive(*, claude_cli: str, shell: str, phrase: str, model: str, timeout: int = 60) -> bool:
    """Invoke claude CLI to send a single keepalive message. Returns True on success."""
    quoted_phrase = shlex.quote(phrase)
    inner = f"{shlex.quote(claude_cli)} -p {quoted_phrase} --model {shlex.quote(model)} --no-session-persistence"
    cmd = [shell, "-lc", inner]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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
