import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .hud_adapters import RESET_GRACE_SECONDS, read_claude_hud, read_oh_my_claude

MAX_CACHE_AGE_SECONDS = 6 * 3600


@dataclass(frozen=True)
class PreciseUsage:
    five_hour_pct: float
    five_hour_resets_at: float
    seven_day_pct: float
    seven_day_resets_at: float
    captured_at: float


def _read_own_cache(cache_path: Path, *, now: float) -> Optional[PreciseUsage]:
    """Read the rate_limits_cache.json our own statusline wrapper maintains.
    Returns None if missing, malformed, too old, or describing a window that
    has already reset."""
    if not cache_path.exists():
        return None
    try:
        raw = json.loads(cache_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    captured_at = raw.get("captured_at", 0)
    if now - captured_at > MAX_CACHE_AGE_SECONDS:
        return None

    five_hour = raw.get("five_hour")
    if not five_hour:
        return None

    resets_at = five_hour.get("resets_at", 0)
    # Same grace as HUD adapter: a reset that just happened should still
    # surface the data so "recovered" alerts can fire (see hud_adapters.py).
    if resets_at < now - RESET_GRACE_SECONDS:
        return None

    seven_day = raw.get("seven_day") or {}
    return PreciseUsage(
        five_hour_pct=float(five_hour.get("used_percentage", 0)),
        five_hour_resets_at=float(resets_at),
        seven_day_pct=float(seven_day.get("used_percentage", 0)),
        seven_day_resets_at=float(seven_day.get("resets_at", 0)),
        captured_at=float(captured_at),
    )


def read_precise(cache_path: Path, *, now: float) -> Optional[PreciseUsage]:
    """Resolve precise usage data through a priority chain:

    1. Our own statusline-wrapper cache (rate_limits_cache.json). Fastest
       path when the user is on Anthropic-direct and Claude Code's
       statusline payload carries fresh rate_limits headers.
    2. claude-hud's usage cache. Fallback for cc-switch / third-party
       users — claude-hud polls Anthropic's OAuth usage API directly using
       the user's credentials, so its cache holds real ground truth even
       when our own statusline-cached rate_limits go stale.
    3. Future HUD adapters (oh-my-claude etc.) plug in here.

    Returns None when no source has fresh data; caller falls back to
    replay_windows estimation.
    """
    direct = _read_own_cache(cache_path, now=now)
    if direct is not None:
        return direct

    for hud_reader in (read_claude_hud, read_oh_my_claude):
        hud = hud_reader(now)
        if hud is not None:
            return PreciseUsage(
                five_hour_pct=hud.five_hour_pct,
                five_hour_resets_at=hud.five_hour_resets_at,
                seven_day_pct=hud.seven_day_pct,
                seven_day_resets_at=hud.seven_day_resets_at,
                captured_at=hud.captured_at,
            )

    return None
