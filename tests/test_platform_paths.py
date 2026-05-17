from pathlib import Path
from quota_monitor.platform import paths
from quota_monitor.platform.paths import (
    user_data_dir, config_file, env_file, state_file,
    claude_app_dir, claude_cli_dir, claude_costs_file, codex_auth_file,
    launch_agent_path,
)


def test_user_data_dir_under_home():
    assert user_data_dir() == Path.home() / ".quota-monitor"


def test_config_and_env_files_in_data_dir():
    assert config_file() == Path.home() / ".quota-monitor" / "config.toml"
    assert env_file() == Path.home() / ".quota-monitor" / ".env"


def test_state_file_in_data_dir():
    assert state_file() == Path.home() / ".quota-monitor" / "state.json"


def test_claude_paths_macos():
    assert claude_app_dir() == Path.home() / "Library" / "Application Support" / "Claude" / "claude-code-sessions"
    assert claude_cli_dir() == Path.home() / ".claude"
    assert claude_costs_file() == Path.home() / ".claude" / "metrics" / "costs.jsonl"


def test_codex_auth_path():
    assert codex_auth_file() == Path.home() / ".codex" / "auth.json"


def test_launch_agent_path_uses_label():
    assert launch_agent_path("io.github.frank.quotamonitor") == \
        Path.home() / "Library" / "LaunchAgents" / "io.github.frank.quotamonitor.plist"


def test_rate_limits_cache():
    p = paths.rate_limits_cache()
    assert str(p).endswith(".quota-monitor/rate_limits_cache.json")


def test_calibration_file():
    p = paths.calibration_file()
    assert str(p).endswith(".quota-monitor/calibration.json")


def test_statusline_original():
    p = paths.statusline_original()
    assert str(p).endswith(".quota-monitor/statusline_original.json")


def test_claude_settings_file():
    p = paths.claude_settings_file()
    assert str(p).endswith(".claude/settings.json")
