import json
from pathlib import Path
from urllib.request import Request, urlopen

from . import ProbeResult

USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"


class CodexAuthMissingError(Exception):
    """Raised when the Codex auth file is missing, malformed, or has no token."""


def scan_codex(*, auth_file: Path) -> ProbeResult:
    if not auth_file.exists():
        raise CodexAuthMissingError(f"{auth_file} not found")
    try:
        auth = json.loads(auth_file.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise CodexAuthMissingError(f"{auth_file} malformed: {e}") from e
    token = (auth.get("tokens") or {}).get("access_token")
    if not token:
        raise CodexAuthMissingError(f"{auth_file} has no access_token")

    req = Request(USAGE_URL, headers={"Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    primary = (data.get("rate_limit") or {}).get("primary_window") or {}
    return ProbeResult(
        source="codex",
        timestamps=(),
        extra={
            "used_percent": primary.get("used_percent", 0),
            "reset_at": primary.get("reset_at"),
        },
    )
