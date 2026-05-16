"""Preflight checks — runs before the wizard does anything mutating."""
import shutil
import subprocess
import sys


def preflight_check(*, need_wrangler: bool = False) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors must be fixed before proceeding."""
    errors: list[str] = []
    warnings: list[str] = []

    if sys.version_info < (3, 11):
        errors.append(f"python>=3.11 required (have {sys.version_info.major}.{sys.version_info.minor})")

    if shutil.which("claude") is None:
        warnings.append("`claude` CLI not in PATH (only needed for keepalive feature)")

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
