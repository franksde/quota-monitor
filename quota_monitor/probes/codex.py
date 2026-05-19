import json
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import ProbeResult
from ._throttled_fetch import FetchHint, should_skip_fetch

USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"


class CodexAuthMissingError(Exception):
    """Raised when the Codex auth file is missing, malformed, or has no token."""


def _read_codex_auth_registry(auth_file: Path, *, now: float) -> Optional[ProbeResult]:
    registry_file = auth_file.parent / "accounts" / "registry.json"
    if not registry_file.exists():
        return None
    try:
        registry = json.loads(registry_file.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    active_key = registry.get("active_account_key")
    accounts = registry.get("accounts")
    if not active_key or not isinstance(accounts, list):
        return None

    active = next(
        (account for account in accounts if account.get("account_key") == active_key),
        None,
    )
    if not isinstance(active, dict):
        return None

    primary = ((active.get("last_usage") or {}).get("primary") or {})
    used_percent = primary.get("used_percent")
    reset_at = primary.get("resets_at", primary.get("reset_at"))
    if not isinstance(used_percent, (int, float)) or not isinstance(reset_at, (int, float)):
        return None
    if reset_at <= now:
        return None

    return ProbeResult(
        source="codex",
        timestamps=(),
        extra={
            "used_percent": int(used_percent),
            "reset_at": int(reset_at),
            "fetched": False,
            "source": "codex-auth",
        },
    )


def scan_codex(
    *,
    auth_file: Path,
    now: float,
    hint: Optional[FetchHint] = None,
    threshold_percent: int = 30,
    base_interval_seconds: int = 300,
) -> ProbeResult:
    if should_skip_fetch(
        hint=hint,
        threshold_percent=threshold_percent,
        now=now,
        base_interval_seconds=base_interval_seconds,
    ):
        assert hint is not None
        return ProbeResult(
            source="codex",
            timestamps=(),
            extra={
                "used_percent": hint.last_used_percent,
                "reset_at": hint.last_reset_at,
                "fetched": False,
            },
        )

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
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError):
        fallback = _read_codex_auth_registry(auth_file, now=now)
        if fallback is not None:
            return fallback
        if hint is not None and hint.last_reset_at > now:
            return ProbeResult(
                source="codex",
                timestamps=(),
                extra={
                    "used_percent": hint.last_used_percent,
                    "reset_at": hint.last_reset_at,
                    "fetched": False,
                    "source": "last-success",
                },
            )
        return ProbeResult(
            source="codex",
            timestamps=(),
            extra={
                "used_percent": 0,
                "reset_at": None,
                "fetched": False,
                "source": "unavailable",
            },
        )

    primary = (data.get("rate_limit") or {}).get("primary_window") or {}
    return ProbeResult(
        source="codex",
        timestamps=(),
        extra={
            "used_percent": primary.get("used_percent", 0),
            "reset_at": primary.get("reset_at"),
            "fetched": True,
        },
    )
