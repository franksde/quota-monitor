import json
import time

from quota_monitor.probes.precise import PreciseUsage, read_precise


def _write_cache(tmp_path, data):
    path = tmp_path / "rate_limits_cache.json"
    path.write_text(json.dumps(data))
    return path


def test_read_precise_returns_none_if_missing(tmp_path):
    result = read_precise(tmp_path / "missing.json", now=time.time())
    assert result is None


def test_read_precise_returns_none_if_malformed(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("not json")
    assert read_precise(path, now=time.time()) is None


def test_read_precise_returns_none_if_five_hour_expired(tmp_path):
    now = 2000.0
    path = _write_cache(tmp_path, {
        "captured_at": 1000.0,
        "five_hour": {"used_percentage": 50.0, "resets_at": 1500.0},
        "seven_day": {"used_percentage": 20.0, "resets_at": 9999.0},
    })
    assert read_precise(path, now=now) is None


def test_read_precise_returns_none_if_captured_too_old(tmp_path):
    now = 30000.0
    path = _write_cache(tmp_path, {
        "captured_at": 1000.0,
        "five_hour": {"used_percentage": 50.0, "resets_at": 99999.0},
        "seven_day": {"used_percentage": 20.0, "resets_at": 99999.0},
    })
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
