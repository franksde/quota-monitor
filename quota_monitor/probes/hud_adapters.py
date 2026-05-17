"""Adapters that reuse caches maintained by third-party Claude Code HUD tools.

Motivation: tools like claude-hud already call Anthropic's /api/oauth/usage
endpoint (using the user's OAuth token) and cache the result locally so they
can render fresh quota bars in the statusline. quota-monitor needs the exact
same data for its alert decisions. Rather than re-implement the OAuth dance,
piggyback on whichever HUD the user already runs.

Freshness rule for HUD caches: a cache entry is valid as long as the reset
timestamp it carries is still in the future. captured_at age does NOT decay
the data — the reset time is a hard fact, not a measurement. (Usage
percentage may be stale by a few points if the HUD hasn't re-polled in a
while; that's acceptable, the worst case is a one-tick delay in alerting
because the HUD's own 5-min TTL will refresh it shortly.)

Adding a new HUD: create read_<toolname>(now, *, home=...) returning an
HudUsageData or None, then plug it into the precise.py fallback chain.
"""
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


# Allow data that describes a reset within this many seconds in the past.
# All caches in the chain (claude-hud, our own wrapper) are passive: they
# only refresh when the user is active in Claude Code. The user is typically
# idle around reset time (they've burned the window and are waiting), so
# nobody re-polls Anthropic — cache freshness can lag 30+ minutes past the
# actual reset moment. The reset *value* in the cache is a hard fact and
# doesn't decay, so generously honour data that describes a reset up to
# 30 minutes ago. This is also the upper bound for how late a "quota
# recovered" notification still feels useful (vs. spammy).
RESET_GRACE_SECONDS = 30 * 60


@dataclass(frozen=True)
class HudUsageData:
    five_hour_pct: float
    five_hour_resets_at: float   # epoch seconds
    seven_day_pct: float
    seven_day_resets_at: float   # epoch seconds
    captured_at: float           # epoch seconds, when the HUD wrote this cache
    source: str                  # which HUD tool ("claude-hud", ...)


def _parse_iso8601_to_epoch(s) -> Optional[float]:
    """Accepts ISO 8601 with optional trailing 'Z'. Returns None on any failure."""
    if not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def read_claude_hud(now: float, *, home: Optional[Path] = None) -> Optional[HudUsageData]:
    """Probe ~/.claude/plugins/claude-hud/.usage-cache.json.

    Returns None when the file is missing, malformed, lacks required fields,
    or describes a 5h window that has already reset (claude-hud hasn't
    re-polled yet, so its cached fiveHourResetAt points into the past).
    """
    home = home or Path.home()
    cache_path = home / ".claude" / "plugins" / "claude-hud" / ".usage-cache.json"
    if not cache_path.exists():
        return None
    try:
        raw = json.loads(cache_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    timestamp_ms = raw.get("timestamp")
    if not isinstance(timestamp_ms, (int, float)) or timestamp_ms <= 0:
        return None
    captured_at = float(timestamp_ms) / 1000.0

    data = raw.get("data") or {}
    five_hour_pct = data.get("fiveHour")
    seven_day_pct = data.get("sevenDay")
    if not isinstance(five_hour_pct, (int, float)) or not isinstance(seven_day_pct, (int, float)):
        return None

    five_hour_resets_at = _parse_iso8601_to_epoch(data.get("fiveHourResetAt"))
    seven_day_resets_at = _parse_iso8601_to_epoch(data.get("sevenDayResetAt"))
    if five_hour_resets_at is None or seven_day_resets_at is None:
        return None

    # Reset must still be in the future, OR very recently past (grace).
    # Without the grace, every reset event creates a dead window of up to
    # 5 minutes where precise data is unreachable and the "recovered"
    # alert can't fire.
    if five_hour_resets_at < now - RESET_GRACE_SECONDS:
        return None

    return HudUsageData(
        five_hour_pct=float(five_hour_pct),
        five_hour_resets_at=five_hour_resets_at,
        seven_day_pct=float(seven_day_pct),
        seven_day_resets_at=seven_day_resets_at,
        captured_at=captured_at,
        source="claude-hud",
    )
