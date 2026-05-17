from pathlib import Path
import pytest
from quota_monitor.config.loader import load_config, ConfigError

FIXTURES = Path(__file__).parent / "fixtures" / "config"


def test_loads_valid_config(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_CHAT_ID=cid\n")
    cfg = load_config(FIXTURES / "valid.toml", env)
    assert cfg.locale == "en"
    assert cfg.probes.claude.enabled is True
    assert cfg.probes.claude.threshold_turns == 5
    assert cfg.probes.claude.precise_threshold_percent == 30
    assert cfg.probes.codex.enabled is False
    assert cfg.notifiers.primary == "telegram"
    assert cfg.notifiers.fallback == "macos_native"
    assert cfg.keepalive.enabled is False
    assert cfg.keepalive.strategy == "seamless"
    assert cfg.secrets["TELEGRAM_BOT_TOKEN"] == "tok"
    assert cfg.secrets["TELEGRAM_CHAT_ID"] == "cid"


def test_rejects_empty_primary_notifier():
    with pytest.raises(ConfigError, match="primary"):
        load_config(FIXTURES / "missing_primary.toml", env_path=None)


def test_missing_config_file_raises_clearly(tmp_path):
    with pytest.raises(ConfigError, match="config file not found"):
        load_config(tmp_path / "nope.toml", env_path=None)


def test_invalid_strategy_rejected(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text(
        '[notifiers]\nprimary="telegram"\n[keepalive]\nstrategy="wat"\n'
    )
    with pytest.raises(ConfigError, match="strategy"):
        load_config(bad, env_path=None)


def test_custom_claude_precise_threshold_percent(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text("""
[probes.claude]
precise_threshold_percent = 45
[notifiers]
primary = "telegram"
""")
    cfg = load_config(cfg_path, env_path=None)
    assert cfg.probes.claude.precise_threshold_percent == 45


def test_rejects_invalid_claude_precise_threshold_percent(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text("""
[probes.claude]
precise_threshold_percent = 101
[notifiers]
primary = "telegram"
""")
    with pytest.raises(ConfigError, match="precise_threshold_percent"):
        load_config(cfg_path, env_path=None)


def test_missing_env_file_is_ok(tmp_path):
    cfg = load_config(FIXTURES / "valid.toml", env_path=tmp_path / "no.env")
    assert cfg.secrets == {}
