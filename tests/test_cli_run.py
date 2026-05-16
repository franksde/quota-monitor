from pathlib import Path
from unittest.mock import patch, MagicMock
import json
from quota_monitor.cli.run import run_once


def _write_config(tmp_path: Path) -> Path:
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
enabled = false
strategy = "polling"
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
strategy = "polling"
model = "haiku"
phrase_pool = ["probe"]
""")
    return cfg


def _write_env(tmp_path: Path) -> Path:
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_CHAT_ID=cid\n")
    return env


def test_run_once_writes_alerted_state_on_success(tmp_path):
    cfg_path = _write_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    fake_probe_result = MagicMock(source="claude", timestamps=(1000.0,) * 6, extra={})
    with patch("quota_monitor.cli.run.scan_claude", return_value=fake_probe_result), \
         patch("quota_monitor.cli.run.TelegramNotifier") as TG:
        tg_instance = MagicMock(name="telegram"); tg_instance.name = "telegram"
        TG.return_value = tg_instance
        rc = run_once(
            config_path=cfg_path, env_path=env_path, state_path=state_path,
            now=1010.0, dry_run=False,
        )
    assert rc == 0
    tg_instance.send.assert_called_once()
    saved = json.loads(state_path.read_text())
    assert saved["claude"]["alerted_for_reset"] == 1000 + 5 * 3600


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


def test_run_once_runs_polling_keepalive_when_enabled(tmp_path, capsys):
    cfg_path = _write_keepalive_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    now = 20_000.0
    fake = MagicMock(source="claude", timestamps=(now - 6 * 3600,), extra={})
    with patch("quota_monitor.cli.run.scan_claude", return_value=fake), \
         patch("quota_monitor.keepalive.polling.run_keepalive", return_value=True) as keepalive:
        rc = run_once(config_path=cfg_path, env_path=env_path, state_path=state_path, now=now, dry_run=False)
    assert rc == 0
    keepalive.assert_called_once()
    saved = json.loads(state_path.read_text())
    assert saved["keepalive"]["phrase_pool_size_at_init"] == 1
    assert saved["keepalive"]["phrase_pool_used_indices"] == [0]
    assert "[info] keepalive sent: probe" in capsys.readouterr().out


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
    # Pre-seed state as if already alerted for this reset point (1000 + 5h).
    state_path.write_text(json.dumps({
        "schema_version": 1,
        "claude": {"alerted_for_reset": 1000 + 5 * 3600},
        "codex": {"alerted_for_reset": 0, "cooldown_until": 0},
        "keepalive": {"last_seamless_scheduled_for": 0, "phrase_pool_used_indices": [], "phrase_pool_size_at_init": 0},
    }))
    fake = MagicMock(source="claude", timestamps=(1000.0,) * 6, extra={})
    with patch("quota_monitor.cli.run.scan_claude", return_value=fake), \
         patch("quota_monitor.cli.run.TelegramNotifier") as TG:
        tg_instance = MagicMock(); tg_instance.name = "telegram"
        TG.return_value = tg_instance
        rc = run_once(config_path=cfg_path, env_path=env_path, state_path=state_path, now=1010.0, dry_run=False)
    assert rc == 0
    tg_instance.send.assert_not_called()
