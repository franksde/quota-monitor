"""Preflight checks — runs before the wizard does anything mutating."""
import shutil
import subprocess
import sys


def _find_tmux() -> bool:
    """Match the resolution logic seamless.py uses at runtime — shutil.which
    plus the brew/macports fallback paths that launchd's default PATH excludes."""
    if shutil.which("tmux"):
        return True
    import os
    for candidate in ("/opt/homebrew/bin/tmux", "/usr/local/bin/tmux", "/opt/local/bin/tmux"):
        if os.path.exists(candidate):
            return True
    return False


def preflight_check(*, need_wrangler: bool = False) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors must be fixed before proceeding.

    keepalive optional deps (claude CLI, tmux) are warnings even when present:
    the wizard runs preflight before the user has chosen whether to enable
    keepalive, and seamless_tick has its own runtime guard (FAILED_NO_TMUX)
    that surfaces a clear install hint if the user does enable it without
    these tools.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if sys.version_info < (3, 11):
        errors.append(f"python>=3.11 required (have {sys.version_info.major}.{sys.version_info.minor})")

    if shutil.which("claude") is None:
        warnings.append("`claude` CLI not in PATH (only needed for keepalive feature)")

    if not _find_tmux():
        warnings.append("`tmux` not in PATH (only needed for keepalive); install with: brew install tmux")

    if need_wrangler and shutil.which("wrangler") is None:
        errors.append("`wrangler` CLI required for Cloudflare relay setup; run: npm install -g wrangler")

    if need_wrangler:
        try:
            result = subprocess.run(["wrangler", "whoami"], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                errors.append("not logged in to Cloudflare; run: wrangler login")
        except FileNotFoundError:
            pass  # already covered above

    return errors, warnings
