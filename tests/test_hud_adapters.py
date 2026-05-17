"""Tests for HUD-tool adapter chain.

Architecture context: third-party statusline tools (claude-hud, etc.) already
query Anthropic's OAuth usage API directly and cache the result locally. For
quota-monitor users who run those tools, reading the existing cache is far
cheaper and far more reliable than reproducing the OAuth dance ourselves.
This module probes those caches as a fallback when our own statusline-wrapper
cache is unavailable or describes a window that has already reset.

Freshness rule: a cache entry is "fresh enough" when the reset timestamp it
describes is still in the future. captured_at age is irrelevant — the reset
moment is a hard fact, not a measurement that decays.
"""
import json
from pathlib import Path

import pytest

from quota_monitor.probes.hud_adapters import (
    HudUsageData, read_claude_hud, read_oh_my_claude,
)


def _write_claude_hud_cache(home: Path, *, data: dict, timestamp_ms: int) -> None:
    p = home / ".claude" / "plugins" / "claude-hud" / ".usage-cache.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"data": data, "timestamp": timestamp_ms}))


def test_returns_data_when_reset_is_in_future(tmp_path):
    now = 1779000000.0
    _write_claude_hud_cache(
        tmp_path,
        data={
            "fiveHour": 63,
            "sevenDay": 58,
            # +1h, +4d
            "fiveHourResetAt": "2026-05-17T18:46:40.000Z",
            "sevenDayResetAt": "2026-05-21T18:00:00.000Z",
        },
        timestamp_ms=int(now * 1000) - 30_000,  # captured 30s ago
    )
    res = read_claude_hud(now, home=tmp_path)
    assert res is not None
    assert res.source == "claude-hud"
    assert res.five_hour_pct == 63.0
    assert res.seven_day_pct == 58.0
    assert res.five_hour_resets_at > now


def test_returns_data_even_when_cache_is_hours_old(tmp_path):
    """captured_at age is irrelevant — reset time is the only freshness signal.
    Regression-pin against the temptation to add an arbitrary TTL."""
    now = 1779000000.0
    _write_claude_hud_cache(
        tmp_path,
        data={
            "fiveHour": 10,
            "sevenDay": 20,
            "fiveHourResetAt": "2026-05-17T18:46:40.000Z",  # +1h in future
            "sevenDayResetAt": "2026-05-21T18:00:00.000Z",
        },
        timestamp_ms=int(now * 1000) - 3 * 3600 * 1000,  # captured 3h ago
    )
    res = read_claude_hud(now, home=tmp_path)
    assert res is not None  # 3h-old cache still valid because reset is in future


def test_returns_none_when_file_missing(tmp_path):
    # No file created at all
    assert read_claude_hud(1779000000.0, home=tmp_path) is None


def test_returns_none_when_json_broken(tmp_path):
    p = tmp_path / ".claude" / "plugins" / "claude-hud" / ".usage-cache.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json")
    assert read_claude_hud(1779000000.0, home=tmp_path) is None


def test_returns_none_when_five_hour_reset_in_past(tmp_path):
    """Window already reset — claude-hud just hasn't re-fetched yet."""
    now = 1779000000.0
    _write_claude_hud_cache(
        tmp_path,
        data={
            "fiveHour": 92,
            "sevenDay": 37,
            "fiveHourResetAt": "2026-05-17T00:00:00.000Z",  # past
            "sevenDayResetAt": "2026-05-21T18:00:00.000Z",
        },
        timestamp_ms=int(now * 1000) - 60_000,
    )
    assert read_claude_hud(now, home=tmp_path) is None


def test_returns_none_when_required_fields_missing(tmp_path):
    now = 1779000000.0
    _write_claude_hud_cache(
        tmp_path,
        data={"fiveHour": 50},  # missing sevenDay, ResetAt fields
        timestamp_ms=int(now * 1000) - 1000,
    )
    assert read_claude_hud(now, home=tmp_path) is None


def test_returns_none_when_iso_timestamp_malformed(tmp_path):
    now = 1779000000.0
    _write_claude_hud_cache(
        tmp_path,
        data={
            "fiveHour": 60,
            "sevenDay": 30,
            "fiveHourResetAt": "not-a-date",
            "sevenDayResetAt": "2026-05-21T18:00:00.000Z",
        },
        timestamp_ms=int(now * 1000) - 1000,
    )
    assert read_claude_hud(now, home=tmp_path) is None


# --- oh-my-claude adapter ---

def _write_omc_cache(home: Path, *, data: dict, timestamp_ms: int) -> None:
    p = home / ".claude" / "plugins" / "oh-my-claudecode" / ".usage-cache-anthropic.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "timestamp": timestamp_ms,
        "data": data,
        "error": False,
        "source": "anthropic",
        "lastSuccessAt": timestamp_ms,
    }))


def test_omc_returns_data_when_reset_in_future(tmp_path):
    now = 1779000000.0
    _write_omc_cache(
        tmp_path,
        data={
            "fiveHourPercent": 71,
            "weeklyPercent": 70,
            "fiveHourResetsAt": "2026-05-17T18:46:40.000Z",  # +1h
            "weeklyResetsAt": "2026-05-21T18:00:00.000Z",
        },
        timestamp_ms=int(now * 1000) - 30_000,
    )
    res = read_oh_my_claude(now, home=tmp_path)
    assert res is not None
    assert res.source == "oh-my-claude"
    assert res.five_hour_pct == 71.0
    assert res.seven_day_pct == 70.0
    assert res.five_hour_resets_at > now


def test_omc_returns_none_when_file_missing(tmp_path):
    assert read_oh_my_claude(1779000000.0, home=tmp_path) is None


def test_omc_returns_none_when_json_broken(tmp_path):
    p = tmp_path / ".claude" / "plugins" / "oh-my-claudecode" / ".usage-cache-anthropic.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not json")
    assert read_oh_my_claude(1779000000.0, home=tmp_path) is None


def test_omc_returns_none_when_five_hour_reset_long_past(tmp_path):
    """User uninstalled omc, cache file lingers with old reset_at. The grace
    check naturally rejects it. Pinning the behaviour because this is exactly
    the situation on the dev's own machine right now."""
    now = 1779000000.0
    _write_omc_cache(
        tmp_path,
        data={
            "fiveHourPercent": 71,
            "weeklyPercent": 70,
            # 5 days ago — definitely past 30-min grace
            "fiveHourResetsAt": "2026-05-12T01:20:00.000Z",
            "weeklyResetsAt": "2026-05-21T18:00:00.000Z",
        },
        timestamp_ms=int(now * 1000) - 5 * 86400 * 1000,
    )
    assert read_oh_my_claude(now, home=tmp_path) is None


def test_omc_returns_none_when_required_fields_missing(tmp_path):
    now = 1779000000.0
    _write_omc_cache(
        tmp_path,
        data={"fiveHourPercent": 71},  # weekly + resets fields missing
        timestamp_ms=int(now * 1000) - 1000,
    )
    assert read_oh_my_claude(now, home=tmp_path) is None
