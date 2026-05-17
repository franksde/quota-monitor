import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


def extract_and_cache_rate_limits(raw_stdin: str, cache_path: Path) -> None:
    try:
        data = json.loads(raw_stdin)
    except (json.JSONDecodeError, TypeError):
        return
    rate_limits = data.get("rate_limits")
    if not rate_limits:
        return

    payload = {"captured_at": time.time()}
    if "five_hour" in rate_limits:
        payload["five_hour"] = rate_limits["five_hour"]
    if "seven_day" in rate_limits:
        payload["seven_day"] = rate_limits["seven_day"]

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload))
        os.replace(tmp, cache_path)
    except OSError:
        pass


def load_original_command(original_path: Path) -> Optional[str]:
    if not original_path.exists():
        return None
    try:
        raw = json.loads(original_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    original = raw.get("original")
    if original is None:
        return None
    if isinstance(original, dict):
        return original.get("command")
    if isinstance(original, str):
        return original
    return None


def run_wrapper(*, cache_path: Path, original_path: Path) -> int:
    raw_stdin = sys.stdin.read()

    extract_and_cache_rate_limits(raw_stdin, cache_path)

    command = load_original_command(original_path)
    if command:
        try:
            result = subprocess.run(
                command,
                input=raw_stdin,
                capture_output=True,
                text=True,
                timeout=5,
                shell=True,
            )
            sys.stdout.write(result.stdout)
        except (subprocess.TimeoutExpired, OSError):
            pass
    return 0
