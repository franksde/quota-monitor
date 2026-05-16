"""Single source of truth for filesystem layout.

macOS-only assumptions live here. Linux support will branch on platform.system().
"""
from pathlib import Path


def user_data_dir() -> Path:
    return Path.home() / ".quota-monitor"


def config_file() -> Path:
    return user_data_dir() / "config.toml"


def env_file() -> Path:
    return user_data_dir() / ".env"


def state_file() -> Path:
    return user_data_dir() / "state.json"


def claude_app_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "Claude" / "claude-code-sessions"


def claude_cli_dir() -> Path:
    return Path.home() / ".claude"


def claude_costs_file() -> Path:
    return claude_cli_dir() / "metrics" / "costs.jsonl"


def codex_auth_file() -> Path:
    return Path.home() / ".codex" / "auth.json"


def launch_agent_path(label: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
