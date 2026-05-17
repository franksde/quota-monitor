from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FetchHint:
    """调用方记录的上次成功 fetch 结果。"""

    last_fetch_at: int
    last_used_percent: int
    last_reset_at: int


def compute_dynamic_interval(
    used_percent: int,
    threshold_percent: int,
    base: int = 300,
) -> int:
    """返回距阈值越远间隔越长的秒数。"""

    distance = max(0, threshold_percent - used_percent)
    if distance >= 20:
        return 20 * 60
    if distance >= 10:
        return 10 * 60
    return base


def should_skip_fetch(
    *,
    hint: Optional[FetchHint],
    threshold_percent: int,
    now: float,
    base_interval_seconds: int = 300,
) -> bool:
    """Decide whether a quota API fetch can be skipped for this tick."""

    if hint is None:
        return False
    if hint.last_reset_at <= now:
        return False
    if hint.last_used_percent >= threshold_percent:
        above_threshold_interval = 30 * 60
        return now - hint.last_fetch_at < above_threshold_interval

    interval = compute_dynamic_interval(
        hint.last_used_percent,
        threshold_percent,
        base=base_interval_seconds,
    )
    return now - hint.last_fetch_at < interval
