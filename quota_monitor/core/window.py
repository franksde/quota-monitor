from dataclasses import dataclass
from typing import Optional

from .state import State
from ..probes import ProbeResult

WINDOW_SECONDS = 5 * 3600


@dataclass(frozen=True)
class LatestWindow:
    start: float
    reset: float
    count: int


@dataclass(frozen=True)
class AlertDecision:
    source: str       # "claude" | "codex"
    reset_at: int     # epoch seconds


def replay_windows(timestamps: tuple[float, ...]) -> Optional[LatestWindow]:
    """Full Replay: scan all timestamps left-to-right, opening a new 5h window
    every time `ts >= current_reset`. Returns the LATEST window after replay,
    or None if there are no timestamps.

    State JSON intentionally does NOT feed in here. The original QuotaMonitor
    used a saved `last_reset_time` to filter history; when that saved value
    drifted into the future, every historical timestamp was filtered out and
    alerts silently stopped. Full Replay makes that failure mode structurally
    impossible.
    """
    if not timestamps:
        return None
    sorted_ts = sorted(timestamps)
    start = sorted_ts[0]
    reset = start + WINDOW_SECONDS
    count = 1
    for ts in sorted_ts[1:]:
        if ts >= reset:
            start = ts
            reset = ts + WINDOW_SECONDS
            count = 1
        else:
            count += 1
    return LatestWindow(start=start, reset=reset, count=count)


def decide_alerts(
    *,
    state: State,
    claude_window: Optional[LatestWindow],
    codex: Optional[ProbeResult],
    now: float,
    claude_threshold: int,
    codex_threshold_percent: int,
) -> list[AlertDecision]:
    decisions: list[AlertDecision] = []

    if claude_window is not None:
        if (
            claude_window.count >= claude_threshold
            and claude_window.reset > now
            and state.claude.alerted_for_reset != int(claude_window.reset)
        ):
            decisions.append(AlertDecision(source="claude", reset_at=int(claude_window.reset)))

    if codex is not None:
        used_percent = int(codex.extra.get("used_percent", 0) or 0)
        reset_at = codex.extra.get("reset_at")
        if (
            reset_at is not None
            and used_percent >= codex_threshold_percent
            and state.codex.cooldown_until <= now
            and state.codex.alerted_for_reset != int(reset_at)
        ):
            decisions.append(AlertDecision(source="codex", reset_at=int(reset_at)))

    return decisions
