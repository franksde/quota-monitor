import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from quota_monitor.cli.run import run_once
from quota_monitor.core.state import save_state, State, ClaudeState
from quota_monitor.probes import ProbeResult
from quota_monitor.probes.precise import PreciseUsage


def _epoch(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def _write_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
locale = "en"
[probes.claude]
enabled = true
threshold_turns = 2
window_hours = 5
precise_threshold_percent = 30
[probes.codex]
enabled = false
[notifiers]
primary = "telegram"
fallback = ""
[notifiers.telegram]
[notifiers.cloudflare_relay]
enabled = false
[keepalive]
enabled = false
strategy = "seamless"
""")
    return cfg


def _write_env(tmp_path: Path) -> Path:
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_CHAT_ID=cid\n")
    return env


def _drift_fixture_timestamps() -> tuple[float, ...]:
    rows = []
    with open("tests/fixtures/claude/drift_2026_05_17_minimal.jsonl", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return tuple(_epoch(row["timestamp"]) for row in rows if row["type"] == "user")


def test_run_once_drift_2026_05_17_uses_cached_known_good_reset_anchor(tmp_path):
    known_reset = _epoch("2026-05-17T05:44:02.457Z")
    state_path = tmp_path / "state.json"
    save_state(
        state_path,
        State(claude=ClaudeState(last_known_good_reset_at=known_reset)),
    )
    captured = {}

    def capture_decision(**kwargs):
        captured["claude_window"] = kwargs["claude_window"]
        return []

    with patch("quota_monitor.cli.run.ensure_wrapper_installed", return_value=False), \
         patch("quota_monitor.cli.run.scan_claude", return_value=ProbeResult("claude", _drift_fixture_timestamps())), \
         patch("quota_monitor.cli.run.read_precise", return_value=None), \
         patch("quota_monitor.cli.run.decide_alerts", side_effect=capture_decision), \
         patch("quota_monitor.cli.run.platform_paths") as mock_paths:
        mock_paths.rate_limits_cache.return_value = tmp_path / "no-cache.json"
        mock_paths.calibration_file.return_value = tmp_path / "calibration.json"
        rc = run_once(
            config_path=_write_config(tmp_path),
            env_path=_write_env(tmp_path),
            state_path=state_path,
            now=_epoch("2026-05-17T05:55:00Z"),
            dry_run=True,
        )

    assert rc == 0
    assert captured["claude_window"].reset == known_reset


def test_run_once_records_known_good_reset_when_precise_data_is_available(tmp_path):
    known_reset = _epoch("2026-05-17T05:44:02.457Z")
    state_path = tmp_path / "state.json"
    precise = PreciseUsage(
        five_hour_pct=20.0,
        five_hour_resets_at=known_reset,
        seven_day_pct=10.0,
        seven_day_resets_at=known_reset + 7 * 24 * 3600,
        captured_at=known_reset - 3600,
    )

    with patch("quota_monitor.cli.run.ensure_wrapper_installed", return_value=False), \
         patch("quota_monitor.cli.run.scan_claude", return_value=ProbeResult("claude", _drift_fixture_timestamps())), \
         patch("quota_monitor.cli.run.read_precise", return_value=precise), \
         patch("quota_monitor.cli.run.platform_paths") as mock_paths, \
         patch("quota_monitor.cli.run.TelegramNotifier") as telegram:
        telegram.return_value = MagicMock(name="telegram")
        telegram.return_value.name = "telegram"
        mock_paths.rate_limits_cache.return_value = tmp_path / "cache.json"
        mock_paths.calibration_file.return_value = tmp_path / "calibration.json"
        rc = run_once(
            config_path=_write_config(tmp_path),
            env_path=_write_env(tmp_path),
            state_path=state_path,
            now=_epoch("2026-05-17T05:20:00Z"),
            dry_run=False,
        )

    assert rc == 0
    saved = json.loads(state_path.read_text())
    assert saved["claude"]["last_known_good_reset_at"] == known_reset
