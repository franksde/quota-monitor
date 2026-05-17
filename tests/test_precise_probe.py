import json
import time
from pathlib import Path
from unittest.mock import patch

from quota_monitor.probes.precise import PreciseUsage, read_precise
from quota_monitor.probes.hud_adapters import HudUsageData


def _write_cache(tmp_path, data):
    path = tmp_path / "rate_limits_cache.json"
    path.write_text(json.dumps(data))
    return path


def test_read_precise_returns_none_if_missing(tmp_path):
    with patch("quota_monitor.probes.precise.read_claude_hud", return_value=None), patch("quota_monitor.probes.precise.read_oh_my_claude", return_value=None):
        result = read_precise(tmp_path / "missing.json", now=time.time())
    assert result is None


def test_read_precise_returns_none_if_malformed(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("not json")
    with patch("quota_monitor.probes.precise.read_claude_hud", return_value=None), patch("quota_monitor.probes.precise.read_oh_my_claude", return_value=None):
        assert read_precise(path, now=time.time()) is None


def test_read_precise_returns_none_if_five_hour_expired_past_grace(tmp_path):
    """reset more than 30 min in the past — definitely stale, drop."""
    now = 10_000.0
    path = _write_cache(tmp_path, {
        "captured_at": now - 100,
        # reset 45 min in the past, past the 30-min grace
        "five_hour": {"used_percentage": 50.0, "resets_at": now - 45 * 60},
        "seven_day": {"used_percentage": 20.0, "resets_at": now + 9999},
    })
    with patch("quota_monitor.probes.precise.read_claude_hud", return_value=None), patch("quota_monitor.probes.precise.read_oh_my_claude", return_value=None):
        assert read_precise(path, now=now) is None


def test_read_precise_returns_none_if_captured_too_old(tmp_path):
    now = 30000.0
    path = _write_cache(tmp_path, {
        "captured_at": 1000.0,
        "five_hour": {"used_percentage": 50.0, "resets_at": 99999.0},
        "seven_day": {"used_percentage": 20.0, "resets_at": 99999.0},
    })
    with patch("quota_monitor.probes.precise.read_claude_hud", return_value=None), patch("quota_monitor.probes.precise.read_oh_my_claude", return_value=None):
        assert read_precise(path, now=now) is None


def test_read_precise_returns_usage_when_valid(tmp_path):
    now = 1000.0
    path = _write_cache(tmp_path, {
        "captured_at": 900.0,
        "five_hour": {"used_percentage": 42.5, "resets_at": 5000.0},
        "seven_day": {"used_percentage": 15.0, "resets_at": 99999.0},
    })
    result = read_precise(path, now=now)
    assert result is not None
    assert isinstance(result, PreciseUsage)
    assert result.five_hour_pct == 42.5
    assert result.five_hour_resets_at == 5000.0
    assert result.seven_day_pct == 15.0
    assert result.seven_day_resets_at == 99999.0
    assert result.captured_at == 900.0


def test_read_precise_tolerates_missing_seven_day(tmp_path):
    now = 1000.0
    path = _write_cache(tmp_path, {
        "captured_at": 900.0,
        "five_hour": {"used_percentage": 42.5, "resets_at": 5000.0},
    })
    result = read_precise(path, now=now)
    assert result is not None
    assert result.seven_day_pct == 0.0
    assert result.seven_day_resets_at == 0.0


# --- HUD adapter fallback chain ---

def _hud(**overrides):
    """Build a fresh HudUsageData with sensible defaults; override specific fields."""
    defaults = dict(
        five_hour_pct=63.0, five_hour_resets_at=10_000.0,
        seven_day_pct=58.0, seven_day_resets_at=99_999.0,
        captured_at=950.0, source="claude-hud",
    )
    defaults.update(overrides)
    return HudUsageData(**defaults)


def test_read_precise_prefers_own_cache_over_hud_when_fresh(tmp_path):
    """When the statusline-wrapper cache is fresh, don't bother reading HUDs."""
    now = 1000.0
    path = _write_cache(tmp_path, {
        "captured_at": 900.0,
        "five_hour": {"used_percentage": 42.5, "resets_at": 5000.0},
        "seven_day": {"used_percentage": 15.0, "resets_at": 99999.0},
    })
    with patch("quota_monitor.probes.precise.read_claude_hud") as hud:
        hud.return_value = _hud(five_hour_pct=99.0)  # would be wrong if used
        result = read_precise(path, now=now)
    assert result.five_hour_pct == 42.5  # own cache won
    hud.assert_not_called()  # didn't even probe HUDs


def test_read_precise_falls_back_to_hud_when_own_cache_missing(tmp_path):
    now = 1000.0
    with patch("quota_monitor.probes.precise.read_claude_hud") as hud, \
         patch("quota_monitor.probes.precise.read_oh_my_claude", return_value=None):
        hud.return_value = _hud()
        result = read_precise(tmp_path / "no-cache.json", now=now)
    assert result is not None
    assert result.five_hour_pct == 63.0      # HUD data
    assert result.five_hour_resets_at == 10_000.0


def test_read_precise_falls_back_to_hud_when_own_cache_reset_past_grace(tmp_path):
    """The cc-switch scenario: wrapper keeps writing stale stdin data with a
    reset_at long in the past. Fall through to HUD which has real data.
    (own cache reset within the 30-min grace WOULD be kept; we test the
    definitely-stale case.)"""
    now = 10_000.0
    path = _write_cache(tmp_path, {
        "captured_at": now - 100,
        # 45 min past — beyond grace
        "five_hour": {"used_percentage": 92.0, "resets_at": now - 45 * 60},
        "seven_day": {"used_percentage": 30.0, "resets_at": now + 99999},
    })
    with patch("quota_monitor.probes.precise.read_claude_hud") as hud, \
         patch("quota_monitor.probes.precise.read_oh_my_claude", return_value=None):
        hud.return_value = _hud()
        result = read_precise(path, now=now)
    assert result is not None
    assert result.five_hour_pct == 63.0  # HUD data, not 92.0


def test_read_precise_falls_back_to_oh_my_claude_when_claude_hud_unavailable(tmp_path):
    """User runs oh-my-claude instead of claude-hud — second HUD in priority
    chain. Pins the chain order: own > claude-hud > oh-my-claude."""
    now = 1000.0
    with patch("quota_monitor.probes.precise.read_claude_hud", return_value=None), \
         patch("quota_monitor.probes.precise.read_oh_my_claude") as omc:
        omc.return_value = _hud(five_hour_pct=71.0, source="oh-my-claude")
        result = read_precise(tmp_path / "no-cache.json", now=now)
    assert result is not None
    assert result.five_hour_pct == 71.0


def test_read_precise_prefers_claude_hud_over_oh_my_claude(tmp_path):
    """Both HUDs present — claude-hud (priority 2) wins over omc (priority 3)."""
    now = 1000.0
    with patch("quota_monitor.probes.precise.read_claude_hud") as hud, \
         patch("quota_monitor.probes.precise.read_oh_my_claude") as omc:
        hud.return_value = _hud(five_hour_pct=63.0, source="claude-hud")
        omc.return_value = _hud(five_hour_pct=99.0, source="oh-my-claude")  # would be wrong if used
        result = read_precise(tmp_path / "no-cache.json", now=now)
    assert result.five_hour_pct == 63.0
    omc.assert_not_called()  # short-circuit after claude-hud hit


def test_read_precise_returns_none_when_all_sources_unavailable(tmp_path):
    now = 1000.0
    with patch("quota_monitor.probes.precise.read_claude_hud", return_value=None), \
         patch("quota_monitor.probes.precise.read_oh_my_claude", return_value=None):
        result = read_precise(tmp_path / "no-cache.json", now=now)
    assert result is None
