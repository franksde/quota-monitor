import json
import stat
from pathlib import Path
from unittest.mock import patch
from quota_monitor.cli.setup import _collect_interactive_answers, run_wizard

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
    assert "precise_threshold_percent = 30" in cfg_text
    assert "[notifiers.cloudflare_relay]" in cfg_text
    assert "[keepalive]" in cfg_text
    env_text = env_path.read_text()
    assert "TELEGRAM_BOT_TOKEN=TEST_TOKEN" in env_text
    assert "TELEGRAM_CHAT_ID=TEST_CHAT" in env_text
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700


def test_wizard_sends_requested_test_notification(tmp_path):
    answers = json.loads((FIXTURES / "wizard_answers_basic.json").read_text())
    answers["skip_telegram_test"] = False
    config_path = tmp_path / "config.toml"
    env_path = tmp_path / ".env"
    with patch("quota_monitor.cli.setup.preflight_check", return_value=([], [])), \
         patch("quota_monitor.cli.setup.send_test", create=True, return_value=0) as send_test:
        rc = run_wizard(
            answers=answers,
            config_path=config_path,
            env_path=env_path,
            data_dir=tmp_path,
            non_interactive=True,
        )
    assert rc == 0
    send_test.assert_called_once_with(config_path=config_path, env_path=env_path, backend="telegram")


def test_wizard_schedules_cf_setup_test_in_configured_locale(tmp_path):
    answers = json.loads((FIXTURES / "wizard_answers_basic.json").read_text())
    answers.update({
        "locale": "zh",
        "primary": "cloudflare_relay",
        "cloudflare_webhook_url": "https://relay.example.com/api/schedule",
    })
    config_path = tmp_path / "config.toml"
    env_path = tmp_path / ".env"
    requests = []

    def fake_urlopen(req, timeout):
        requests.append(req)
        class Response:
            def close(self): pass
        return Response()

    with patch("quota_monitor.cli.setup.preflight_check", return_value=([], [])), \
         patch("urllib.request.urlopen", side_effect=fake_urlopen):
        rc = run_wizard(
            answers=answers,
            config_path=config_path,
            env_path=env_path,
            data_dir=tmp_path,
            non_interactive=True,
        )
    assert rc == 0
    assert requests
    payload = json.loads(requests[0].data.decode())
    assert "测试" in payload["message"]
    assert "Cloudflare" in payload["message"]


def test_interactive_wizard_reuses_existing_telegram_env():
    with patch("quota_monitor.cli.setup.ask_choice", side_effect=[0, 0, 0, 2]), \
         patch("quota_monitor.cli.setup.ask_yes_no", side_effect=[True, False, True, False, False]), \
         patch("quota_monitor.cli.setup._statusline_wizard_step", return_value=True) as statusline_step, \
         patch("quota_monitor.cli.setup.ask_string", return_value="45") as ask_string:
        answers = _collect_interactive_answers(
            existing_secrets={
                "TELEGRAM_BOT_TOKEN": "EXISTING_TOKEN",
                "TELEGRAM_CHAT_ID": "EXISTING_CHAT",
            }
        )
    ask_string.assert_called_once()
    statusline_step.assert_called_once()
    assert answers["telegram_bot_token"] == "EXISTING_TOKEN"
    assert answers["telegram_chat_id"] == "EXISTING_CHAT"
    assert answers["claude_precise_threshold_percent"] == 45


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
    answers["keepalive_strategy"] = "seamless"
    with patch("quota_monitor.cli.setup.preflight_check", return_value=([], [])):
        rc = run_wizard(
            answers=answers,
            config_path=tmp_path / "config.toml",
            env_path=tmp_path / ".env",
            data_dir=tmp_path,
            non_interactive=True,
        )
    assert rc == 0
    assert 'strategy = "seamless"' in (tmp_path / "config.toml").read_text()
    assert "enabled = true" in (tmp_path / "config.toml").read_text()
