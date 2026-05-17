import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

MAX_CACHE_AGE_SECONDS = 6 * 3600


@dataclass(frozen=True)
class PreciseUsage:
    five_hour_pct: float
    five_hour_resets_at: float
    seven_day_pct: float
    seven_day_resets_at: float
    captured_at: float


def read_precise(cache_path: Path, *, now: float) -> Optional[PreciseUsage]:
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
    if resets_at <= now:
        return None

    seven_day = raw.get("seven_day") or {}
    return PreciseUsage(
        five_hour_pct=float(five_hour.get("used_percentage", 0)),
        five_hour_resets_at=float(resets_at),
        seven_day_pct=float(seven_day.get("used_percentage", 0)),
        seven_day_resets_at=float(seven_day.get("resets_at", 0)),
        captured_at=float(captured_at),
    )
