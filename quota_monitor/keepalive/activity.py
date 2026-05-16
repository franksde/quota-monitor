def is_idle(*, timestamps: tuple[float, ...], now: float, idle_seconds: int) -> bool:
    """True if no timestamp is within `idle_seconds` of `now`."""
    cutoff = now - idle_seconds
    return not any(ts >= cutoff for ts in timestamps)
