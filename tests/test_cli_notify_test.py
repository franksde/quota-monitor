from pathlib import Path
from unittest.mock import patch, MagicMock
from quota_monitor.cli.notify_test import send_test


def _write_minimal_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.toml"
    cfg.write_text('locale="en"\n[notifiers]\nprimary="telegram"\n[notifiers.telegram]\n')
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_CHAT_ID=cid\n")
    return cfg, env


def test_sends_test_alert_via_primary(tmp_path):
    cfg, env = _write_minimal_config(tmp_path)
    with patch("quota_monitor.cli.notify_test.TelegramNotifier") as TG:
        instance = MagicMock(); instance.name = "telegram"
        TG.return_value = instance
        rc = send_test(config_path=cfg, env_path=env, backend=None)
    assert rc == 0
    instance.send.assert_called_once()


def test_send_test_specific_backend(tmp_path):
    cfg, env = _write_minimal_config(tmp_path)
    with patch("quota_monitor.cli.notify_test.MacOSNativeNotifier") as MN:
        instance = MagicMock(); instance.name = "macos_native"
        MN.return_value = instance
        rc = send_test(config_path=cfg, env_path=env, backend="macos_native")
    assert rc == 0
    instance.send.assert_called_once()


def test_send_test_returns_nonzero_on_unknown_backend(tmp_path):
    cfg, env = _write_minimal_config(tmp_path)
    rc = send_test(config_path=cfg, env_path=env, backend="zzz")
    assert rc != 0
