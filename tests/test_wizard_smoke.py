import json
from pathlib import Path
from unittest.mock import patch
from quota_monitor.cli.setup import run_wizard

FIXTURES = Path(__file__).parent / "fixtures"


def test_wizard_non_interactive_writes_config_and_env(tmp_path):
    answers = json.loads((FIXTURES / "wizard_answers_basic.json").read_text())
    config_path = tmp_path / "config.toml"
    env_path = tmp_path / ".env"
    # Skip preflight strictness by stubbing it to "all green".
    with patch("quota_monitor.cli.setup.preflight_check", return_value=([], [])):
        rc = run_wizard(
            answers=answers,
            config_path=config_path,
            env_path=env_path,
            data_dir=tmp_path,
            non_interactive=True,
        )
    assert rc == 0
    cfg_text = config_path.read_text()
    assert 'locale = "en"' in cfg_text
    assert "[notifiers.cloudflare_relay]" in cfg_text
    assert "[keepalive]" in cfg_text
    env_text = env_path.read_text()
    assert "TELEGRAM_BOT_TOKEN=TEST_TOKEN" in env_text
    assert "TELEGRAM_CHAT_ID=TEST_CHAT" in env_text


def test_wizard_aborts_when_preflight_missing_required(tmp_path):
    answers = json.loads((FIXTURES / "wizard_answers_basic.json").read_text())
    with patch("quota_monitor.cli.setup.preflight_check",
               return_value=(["python>=3.11 missing"], [])):
        rc = run_wizard(
            answers=answers,
            config_path=tmp_path / "config.toml",
            env_path=tmp_path / ".env",
            data_dir=tmp_path,
            non_interactive=True,
        )
    assert rc != 0
    assert not (tmp_path / "config.toml").exists()


def test_wizard_keepalive_enabled_writes_strategy(tmp_path):
    answers = json.loads((FIXTURES / "wizard_answers_basic.json").read_text())
    answers["keepalive_enabled"] = True
    answers["keepalive_strategy"] = "polling"
    with patch("quota_monitor.cli.setup.preflight_check", return_value=([], [])):
        rc = run_wizard(
            answers=answers,
            config_path=tmp_path / "config.toml",
            env_path=tmp_path / ".env",
            data_dir=tmp_path,
            non_interactive=True,
        )
    assert rc == 0
    assert 'strategy = "polling"' in (tmp_path / "config.toml").read_text()
    assert "enabled = true" in (tmp_path / "config.toml").read_text()
