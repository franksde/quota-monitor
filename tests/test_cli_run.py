from pathlib import Path
from unittest.mock import patch, MagicMock
import json
from quota_monitor.cli.run import run_once
from quota_monitor.core.state import default_state
from quota_monitor.core.window import WINDOW_SECONDS, RESET_CORRECTION_SECONDS
from quota_monitor.probes import ProbeResult
from quota_monitor.probes._throttled_fetch import FetchHint


def _write_config(tmp_path: Path, *, precise_threshold_percent: int = 30) -> Path:
    cfg = tmp_path / "config.toml"
    cfg.write_text(f"""
locale = "en"
[probes.claude]
enabled = true
threshold_turns = 5
window_hours = 5
precise_threshold_percent = {precise_threshold_percent}
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


def _write_cf_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
locale = "en"
[probes.claude]
enabled = true
threshold_turns = 5
window_hours = 5
precise_threshold_percent = 30
[probes.codex]
enabled = false
[notifiers]
primary = "cloudflare_relay"
fallback = ""
[notifiers.telegram]
[notifiers.cloudflare_relay]
enabled = true
webhook_url = "https://relay.example.com/api/schedule"
[keepalive]
enabled = false
strategy = "seamless"
""")
    return cfg


def _write_keepalive_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
locale = "en"
[probes.claude]
enabled = true
threshold_turns = 5
window_hours = 5
[probes.codex]
enabled = false
[notifiers]
primary = "telegram"
fallback = ""
[notifiers.telegram]
[notifiers.cloudflare_relay]
enabled = false
[keepalive]
enabled = true
strategy = "seamless"
model = "haiku"
phrase_pool = ["probe"]
""")
    return cfg


def _write_codex_config(tmp_path: Path, *, threshold_percent: int = 30) -> Path:
    cfg = tmp_path / "config.toml"
    cfg.write_text(f"""
locale = "en"
[probes.claude]
enabled = false
[probes.codex]
enabled = true
threshold_percent = {threshold_percent}
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


def test_run_once_passes_codex_fetch_hint_from_state(tmp_path):
    cfg_path = _write_codex_config(tmp_path, threshold_percent=42)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "schema_version": 1,
        "claude": {"alerted_for_reset": 0, "cooldown_until": 0},
        "codex": {
            "alerted_for_reset": 0,
            "cooldown_until": 0,
            "last_fetch_at": 1_000,
            "last_used_percent": 12,
            "last_reset_at": 5_000,
        },
        "keepalive": {
            "last_seamless_scheduled_for": 0,
            "phrase_pool_used_indices": [],
            "phrase_pool_size_at_init": 0,
        },
    }))
    fake_codex = ProbeResult(
        source="codex",
        timestamps=(),
        extra={"used_percent": 12, "reset_at": 5_000, "fetched": False},
    )

    with patch("quota_monitor.cli.run.ensure_wrapper_installed", return_value=False), \
         patch("quota_monitor.cli.run.platform_paths.codex_auth_file", return_value=tmp_path / "auth.json"), \
         patch("quota_monitor.cli.run.scan_codex", return_value=fake_codex) as mock_scan:
        rc = run_once(
            config_path=cfg_path,
            env_path=env_path,
            state_path=state_path,
            now=1_100.0,
            dry_run=True,
        )

    assert rc == 0
    assert mock_scan.call_args.kwargs["hint"] == FetchHint(
        last_fetch_at=1_000,
        last_used_percent=12,
        last_reset_at=5_000,
    )
    assert mock_scan.call_args.kwargs["now"] == 1_100.0
    assert mock_scan.call_args.kwargs["threshold_percent"] == 42


def test_run_once_updates_codex_fetch_state_after_successful_fetch(tmp_path):
    cfg_path = _write_codex_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    now = 1_234.0
    fake_codex = ProbeResult(
        source="codex",
        timestamps=(),
        extra={"used_percent": 12, "reset_at": 5_000, "fetched": True},
    )

    with patch("quota_monitor.cli.run.ensure_wrapper_installed", return_value=False), \
         patch("quota_monitor.cli.run.platform_paths.codex_auth_file", return_value=tmp_path / "auth.json"), \
         patch("quota_monitor.cli.run.scan_codex", return_value=fake_codex), \
         patch("quota_monitor.cli.run.TelegramNotifier") as TG:
        tg_instance = MagicMock(name="telegram")
        tg_instance.name = "telegram"
        TG.return_value = tg_instance
        rc = run_once(
            config_path=cfg_path,
            env_path=env_path,
            state_path=state_path,
            now=now,
            dry_run=False,
        )

    assert rc == 0
    saved = json.loads(state_path.read_text())
    assert saved["codex"]["last_fetch_at"] == int(now)
    assert saved["codex"]["last_used_percent"] == 12
    assert saved["codex"]["last_reset_at"] == 5_000


def test_run_once_preserves_codex_fetch_state_when_alert_updates_cooldown(tmp_path):
    cfg_path = _write_codex_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    now = 1_234.0
    fake_codex = ProbeResult(
        source="codex",
        timestamps=(),
        extra={"used_percent": 60, "reset_at": 5_000, "fetched": True},
    )

    with patch("quota_monitor.cli.run.ensure_wrapper_installed", return_value=False), \
         patch("quota_monitor.cli.run.platform_paths.codex_auth_file", return_value=tmp_path / "auth.json"), \
         patch("quota_monitor.cli.run.scan_codex", return_value=fake_codex), \
         patch("quota_monitor.cli.run.TelegramNotifier") as TG:
        tg_instance = MagicMock(name="telegram")
        tg_instance.name = "telegram"
        TG.return_value = tg_instance
        rc = run_once(
            config_path=cfg_path,
            env_path=env_path,
            state_path=state_path,
            now=now,
            dry_run=False,
        )

    assert rc == 0
    tg_instance.send.assert_called_once()
    saved = json.loads(state_path.read_text())
    assert saved["codex"]["alerted_for_reset"] == 5_000
    assert saved["codex"]["cooldown_until"] == 5_000
    assert saved["codex"]["last_fetch_at"] == int(now)
    assert saved["codex"]["last_used_percent"] == 60
    assert saved["codex"]["last_reset_at"] == 5_000


def test_run_once_writes_alerted_state_on_success(tmp_path):
    cfg_path = _write_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    # window start = 1000, reset = 1000 + 18000 + (-300) = 18700
    # new "recovered" model fires when reset has just passed (within 10 min grace)
    expected_reset = 1000 + WINDOW_SECONDS + RESET_CORRECTION_SECONDS
    now = expected_reset + 30  # reset just happened 30s ago
    fake_probe_result = MagicMock(source="claude", timestamps=(1000.0,) * 6, extra={})
    with patch("quota_monitor.cli.run.scan_claude", return_value=fake_probe_result), \
         patch("quota_monitor.cli.run.read_precise", return_value=None), \
         patch("quota_monitor.cli.run.platform_paths") as mock_paths, \
         patch("quota_monitor.cli.run.TelegramNotifier") as TG:
        mock_paths.rate_limits_cache.return_value = tmp_path / "no_cache.json"
        mock_paths.calibration_file.return_value = tmp_path / "cal.json"
        tg_instance = MagicMock(name="telegram"); tg_instance.name = "telegram"
        TG.return_value = tg_instance
        rc = run_once(
            config_path=cfg_path, env_path=env_path, state_path=state_path,
            now=float(now), dry_run=False,
        )
    assert rc == 0
    tg_instance.send.assert_called_once()
    saved = json.loads(state_path.read_text())
    assert saved["claude"]["alerted_for_reset"] == expected_reset
    sent_alert = tg_instance.send.call_args.args[0]
    assert "estimated from local conversation logs" in sent_alert.body


def test_run_once_dry_run_does_not_send_or_save(tmp_path):
    cfg_path = _write_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    fake_probe_result = MagicMock(source="claude", timestamps=(1000.0,) * 6, extra={})
    with patch("quota_monitor.cli.run.scan_claude", return_value=fake_probe_result), \
         patch("quota_monitor.cli.run.TelegramNotifier") as TG:
        tg_instance = MagicMock(); tg_instance.name = "telegram"
        TG.return_value = tg_instance
        rc = run_once(
            config_path=cfg_path, env_path=env_path, state_path=state_path,
            now=1010.0, dry_run=True,
        )
    assert rc == 0
    tg_instance.send.assert_not_called()
    assert not state_path.exists()


def test_run_once_runs_seamless_keepalive_when_enabled(tmp_path):
    cfg_path = _write_keepalive_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    now = 20_000.0
    fake = MagicMock(source="claude", timestamps=(now - 6 * 3600,), extra={})
    with patch("quota_monitor.cli.run.scan_claude", return_value=fake), \
         patch("quota_monitor.keepalive.seamless.seamless_tick", return_value=(MagicMock(), default_state())):
        rc = run_once(config_path=cfg_path, env_path=env_path, state_path=state_path, now=now, dry_run=False)
    assert rc == 0


def test_run_once_returns_nonzero_when_config_missing(tmp_path):
    rc = run_once(
        config_path=tmp_path / "nope.toml",
        env_path=tmp_path / ".env",
        state_path=tmp_path / "state.json",
        now=1010.0, dry_run=False,
    )
    assert rc != 0


def test_run_once_does_not_realert_in_same_window(tmp_path):
    cfg_path = _write_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    # Pre-seed state as if already alerted for this reset point.
    corrected_reset = 1000 + WINDOW_SECONDS + RESET_CORRECTION_SECONDS
    state_path.write_text(json.dumps({
        "schema_version": 1,
        "claude": {"alerted_for_reset": corrected_reset},
        "codex": {"alerted_for_reset": 0, "cooldown_until": 0},
        "keepalive": {"last_seamless_scheduled_for": 0, "phrase_pool_used_indices": [], "phrase_pool_size_at_init": 0},
    }))
    fake = MagicMock(source="claude", timestamps=(1000.0,) * 6, extra={})
    with patch("quota_monitor.cli.run.scan_claude", return_value=fake), \
         patch("quota_monitor.cli.run.read_precise", return_value=None), \
         patch("quota_monitor.cli.run.platform_paths") as mock_paths, \
         patch("quota_monitor.cli.run.TelegramNotifier") as TG:
        mock_paths.rate_limits_cache.return_value = tmp_path / "no_cache.json"
        mock_paths.calibration_file.return_value = tmp_path / "cal.json"
        tg_instance = MagicMock(); tg_instance.name = "telegram"
        TG.return_value = tg_instance
        rc = run_once(config_path=cfg_path, env_path=env_path, state_path=state_path, now=1010.0, dry_run=False)
    assert rc == 0
    tg_instance.send.assert_not_called()


def test_run_once_uses_precise_when_cache_valid(tmp_path, capsys):
    cfg_path = _write_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    cache_path = tmp_path / "rate_limits_cache.json"
    calibration_path = tmp_path / "calibration.json"
    now = 10_000.0
    # New "recovered" model: reset_at must be in the [now-grace, now] window
    # (or strictly equal-ish to now) for the alert to fire.
    reset_at = now - 30  # reset just happened
    cache_path.write_text(json.dumps({
        "captured_at": now - 60,
        "five_hour": {"used_percentage": 80.0, "resets_at": reset_at},
        "seven_day": {"used_percentage": 30.0, "resets_at": now + 86400},
    }))

    fake = MagicMock(source="claude", timestamps=(), extra={})
    with patch("quota_monitor.cli.run.scan_claude", return_value=fake), \
         patch("quota_monitor.cli.run.platform_paths") as mock_paths:
        mock_paths.rate_limits_cache.return_value = cache_path
        mock_paths.calibration_file.return_value = calibration_path
        rc = run_once(
            config_path=cfg_path,
            env_path=env_path,
            state_path=state_path,
            now=now,
            dry_run=True,
        )

    assert rc == 0
    assert f"reset_at={int(reset_at)}" in capsys.readouterr().out


def test_run_once_skips_precise_alert_below_threshold(tmp_path, capsys):
    cfg_path = _write_config(tmp_path, precise_threshold_percent=30)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    cache_path = tmp_path / "rate_limits_cache.json"
    calibration_path = tmp_path / "calibration.json"
    now = 10_000.0
    cache_path.write_text(json.dumps({
        "captured_at": now - 60,
        "five_hour": {"used_percentage": 20.0, "resets_at": now + 3600},
        "seven_day": {"used_percentage": 30.0, "resets_at": now + 86400},
    }))

    fake = MagicMock(source="claude", timestamps=(), extra={})
    with patch("quota_monitor.cli.run.scan_claude", return_value=fake), \
         patch("quota_monitor.cli.run.platform_paths") as mock_paths:
        mock_paths.rate_limits_cache.return_value = cache_path
        mock_paths.calibration_file.return_value = calibration_path
        rc = run_once(
            config_path=cfg_path,
            env_path=env_path,
            state_path=state_path,
            now=now,
            dry_run=True,
        )

    assert rc == 0
    assert "[dry-run] would alert" not in capsys.readouterr().out


def test_run_once_precise_alert_omits_estimated_suffix(tmp_path):
    cfg_path = _write_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    cache_path = tmp_path / "rate_limits_cache.json"
    calibration_path = tmp_path / "calibration.json"
    now = 10_000.0
    reset_at = now - 30  # just-passed reset triggers under new model
    cache_path.write_text(json.dumps({
        "captured_at": now - 60,
        "five_hour": {"used_percentage": 80.0, "resets_at": reset_at},
        "seven_day": {"used_percentage": 30.0, "resets_at": now + 86400},
    }))

    fake = MagicMock(source="claude", timestamps=(), extra={})
    with patch("quota_monitor.cli.run.scan_claude", return_value=fake), \
         patch("quota_monitor.cli.run.platform_paths") as mock_paths, \
         patch("quota_monitor.cli.run.TelegramNotifier") as TG:
        tg_instance = MagicMock(name="telegram")
        tg_instance.name = "telegram"
        TG.return_value = tg_instance
        mock_paths.rate_limits_cache.return_value = cache_path
        mock_paths.calibration_file.return_value = calibration_path
        rc = run_once(
            config_path=cfg_path,
            env_path=env_path,
            state_path=state_path,
            now=now,
            dry_run=False,
        )

    assert rc == 0
    sent_alert = tg_instance.send.call_args.args[0]
    assert "estimated from local conversation logs" not in sent_alert.body


def test_run_once_records_calibration_sample_when_precise_and_computed_match(tmp_path):
    cfg_path = _write_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    cache_path = tmp_path / "rate_limits_cache.json"
    calibration_path = tmp_path / "calibration.json"
    now = 10_000.0
    computed_start = 9_000.0
    precise_reset = computed_start + 5 * 3600 - 300
    cache_path.write_text(json.dumps({
        "captured_at": now - 60,
        "five_hour": {"used_percentage": 80.0, "resets_at": precise_reset},
        "seven_day": {"used_percentage": 30.0, "resets_at": now + 86400},
    }))

    fake = MagicMock(source="claude", timestamps=(computed_start,) * 5, extra={})
    with patch("quota_monitor.cli.run.scan_claude", return_value=fake), \
         patch("quota_monitor.cli.run.platform_paths") as mock_paths:
        mock_paths.rate_limits_cache.return_value = cache_path
        mock_paths.calibration_file.return_value = calibration_path
        rc = run_once(
            config_path=cfg_path,
            env_path=env_path,
            state_path=state_path,
            now=now,
            dry_run=True,
        )

    assert rc == 0
    calibration = json.loads(calibration_path.read_text())
    assert len(calibration["samples"]) == 1
    assert calibration["samples"][0]["precise_reset"] == precise_reset
    assert calibration["samples"][0]["computed_reset"] == computed_start + 5 * 3600


# --- CF Queue mode: schedule-ahead alerts ---

def test_cf_mode_schedules_alert_when_precise_threshold_hit(tmp_path):
    """CF mode: precise pct >= threshold → fire send() with future reset_at.
    CF Worker will hold it via delaySeconds and deliver at reset_at."""
    cfg_path = _write_cf_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    cache_path = tmp_path / "rate_limits_cache.json"
    now = 10_000.0
    future_reset = now + 3600  # 1h ahead
    cache_path.write_text(json.dumps({
        "captured_at": now - 60,
        "five_hour": {"used_percentage": 80.0, "resets_at": future_reset},
        "seven_day": {"used_percentage": 30.0, "resets_at": now + 86400},
    }))

    fake = MagicMock(source="claude", timestamps=(now - 100,) * 10, extra={})
    with patch("quota_monitor.cli.run.scan_claude", return_value=fake), \
         patch("quota_monitor.cli.run.platform_paths") as mock_paths, \
         patch("quota_monitor.cli.run.CloudflareRelayNotifier") as CF:
        cf_instance = MagicMock(name="cf")
        cf_instance.name = "cloudflare_relay"
        CF.return_value = cf_instance
        mock_paths.rate_limits_cache.return_value = cache_path
        mock_paths.calibration_file.return_value = tmp_path / "cal.json"
        rc = run_once(
            config_path=cfg_path, env_path=env_path, state_path=state_path,
            now=now, dry_run=False,
        )

    assert rc == 0
    cf_instance.send.assert_called_once()
    sent_alert = cf_instance.send.call_args.args[0]
    assert sent_alert.reset_at == int(future_reset)
    saved = json.loads(state_path.read_text())
    assert saved["claude"]["scheduled_alert_reset_at"] == int(future_reset)


def test_cf_mode_dedupes_same_reset(tmp_path):
    """Second LaunchAgent tick with same future reset → don't re-schedule."""
    cfg_path = _write_cf_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    cache_path = tmp_path / "rate_limits_cache.json"
    now = 10_000.0
    future_reset = now + 3600
    cache_path.write_text(json.dumps({
        "captured_at": now - 60,
        "five_hour": {"used_percentage": 80.0, "resets_at": future_reset},
        "seven_day": {"used_percentage": 30.0, "resets_at": now + 86400},
    }))
    # pre-seed state as already scheduled
    state_path.write_text(json.dumps({
        "schema_version": 1,
        "claude": {
            "alerted_for_reset": 0, "cooldown_until": 0,
            "last_known_good_reset_at": 0,
            "scheduled_alert_reset_at": int(future_reset),
        },
        "codex": {"alerted_for_reset": 0, "cooldown_until": 0},
        "keepalive": {"last_seamless_scheduled_for": 0, "phrase_pool_used_indices": [], "phrase_pool_size_at_init": 0},
    }))

    fake = MagicMock(source="claude", timestamps=(now - 100,) * 10, extra={})
    with patch("quota_monitor.cli.run.scan_claude", return_value=fake), \
         patch("quota_monitor.cli.run.platform_paths") as mock_paths, \
         patch("quota_monitor.cli.run.CloudflareRelayNotifier") as CF:
        cf_instance = MagicMock(name="cf")
        cf_instance.name = "cloudflare_relay"
        CF.return_value = cf_instance
        mock_paths.rate_limits_cache.return_value = cache_path
        mock_paths.calibration_file.return_value = tmp_path / "cal.json"
        rc = run_once(
            config_path=cfg_path, env_path=env_path, state_path=state_path,
            now=now, dry_run=False,
        )

    assert rc == 0
    cf_instance.send.assert_not_called()  # dedupe kicked in


def test_cf_mode_schedules_when_only_jsonl_turns_hit(tmp_path):
    """No precise data, but enough jsonl turns → schedule based on estimated
    reset. Covers "user closed terminal, we still send out something" goal."""
    cfg_path = _write_cf_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    now = 10_000.0
    # 10 timestamps right before now, no precise → estimated path
    timestamps = tuple(now - i * 60 for i in range(10))
    fake = MagicMock(source="claude", timestamps=timestamps, extra={})

    with patch("quota_monitor.cli.run.scan_claude", return_value=fake), \
         patch("quota_monitor.cli.run.read_precise", return_value=None), \
         patch("quota_monitor.cli.run.platform_paths") as mock_paths, \
         patch("quota_monitor.cli.run.CloudflareRelayNotifier") as CF:
        cf_instance = MagicMock(name="cf")
        cf_instance.name = "cloudflare_relay"
        CF.return_value = cf_instance
        mock_paths.rate_limits_cache.return_value = tmp_path / "no_cache.json"
        mock_paths.calibration_file.return_value = tmp_path / "cal.json"
        rc = run_once(
            config_path=cfg_path, env_path=env_path, state_path=state_path,
            now=now, dry_run=False,
        )

    assert rc == 0
    cf_instance.send.assert_called_once()
    sent_alert = cf_instance.send.call_args.args[0]
    assert sent_alert.reset_at > now  # future


def test_cf_mode_skips_when_no_data_at_all(tmp_path):
    """No precise, no jsonl, no anchor → don't schedule anything."""
    cfg_path = _write_cf_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    now = 10_000.0
    fake = MagicMock(source="claude", timestamps=(), extra={})

    with patch("quota_monitor.cli.run.scan_claude", return_value=fake), \
         patch("quota_monitor.cli.run.read_precise", return_value=None), \
         patch("quota_monitor.cli.run.platform_paths") as mock_paths, \
         patch("quota_monitor.cli.run.CloudflareRelayNotifier") as CF:
        cf_instance = MagicMock(name="cf")
        cf_instance.name = "cloudflare_relay"
        CF.return_value = cf_instance
        mock_paths.rate_limits_cache.return_value = tmp_path / "no_cache.json"
        mock_paths.calibration_file.return_value = tmp_path / "cal.json"
        rc = run_once(
            config_path=cfg_path, env_path=env_path, state_path=state_path,
            now=now, dry_run=False,
        )

    assert rc == 0
    cf_instance.send.assert_not_called()


def test_cf_mode_dry_run_does_not_send(tmp_path):
    cfg_path = _write_cf_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    cache_path = tmp_path / "rate_limits_cache.json"
    now = 10_000.0
    cache_path.write_text(json.dumps({
        "captured_at": now - 60,
        "five_hour": {"used_percentage": 80.0, "resets_at": now + 3600},
        "seven_day": {"used_percentage": 30.0, "resets_at": now + 86400},
    }))

    fake = MagicMock(source="claude", timestamps=(now - 100,) * 10, extra={})
    with patch("quota_monitor.cli.run.scan_claude", return_value=fake), \
         patch("quota_monitor.cli.run.platform_paths") as mock_paths, \
         patch("quota_monitor.cli.run.CloudflareRelayNotifier") as CF:
        cf_instance = MagicMock(name="cf")
        cf_instance.name = "cloudflare_relay"
        CF.return_value = cf_instance
        mock_paths.rate_limits_cache.return_value = cache_path
        mock_paths.calibration_file.return_value = tmp_path / "cal.json"
        rc = run_once(
            config_path=cfg_path, env_path=env_path, state_path=state_path,
            now=now, dry_run=True,
        )

    assert rc == 0
    cf_instance.send.assert_not_called()
    assert not state_path.exists()
