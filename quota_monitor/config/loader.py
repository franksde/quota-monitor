import tomllib
from pathlib import Path

from .dotenv import parse_dotenv
from .schema import (
    ClaudeProbeConfig,
    CloudflareRelayConfig,
    CodexProbeConfig,
    Config,
    KeepaliveConfig,
    NotifiersConfig,
    ProbesConfig,
    VALID_LOCALES,
    VALID_STRATEGIES,
)


class ConfigError(Exception):
    """Raised when configuration is invalid or unreadable."""


def load_config(toml_path: Path, env_path: Path | None) -> Config:
    if not toml_path.exists():
        raise ConfigError(f"config file not found: {toml_path}. Run `quota-monitor setup`.")

    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"config file is not valid TOML: {e}")

    locale = data.get("locale", "en")
    if locale not in VALID_LOCALES:
        raise ConfigError(f"locale must be one of {VALID_LOCALES}, got {locale!r}")

    probes_block = data.get("probes", {})
    probes = ProbesConfig(
        claude=ClaudeProbeConfig(**(probes_block.get("claude") or {})),
        codex=CodexProbeConfig(**(probes_block.get("codex") or {})),
    )

    notifiers_block = data.get("notifiers", {})
    primary = notifiers_block.get("primary", "")
    if not primary:
        raise ConfigError("notifiers.primary must not be empty")
    cf = CloudflareRelayConfig(**(notifiers_block.get("cloudflare_relay") or {}))
    notifiers = NotifiersConfig(
        primary=primary,
        fallback=notifiers_block.get("fallback", ""),
        cloudflare_relay=cf,
    )

    ka_block = data.get("keepalive", {}) or {}
    if "phrase_pool" in ka_block:
        ka_block = {**ka_block, "phrase_pool": tuple(ka_block["phrase_pool"])}
    keepalive = KeepaliveConfig(**ka_block)
    if keepalive.strategy not in VALID_STRATEGIES:
        raise ConfigError(
            f"keepalive.strategy must be one of {VALID_STRATEGIES}, got {keepalive.strategy!r}"
        )

    secrets: dict[str, str] = {}
    if env_path is not None and env_path.exists():
        secrets = parse_dotenv(env_path.read_text())

    return Config(
        locale=locale,
        log_level=data.get("log_level", "info"),
        probes=probes,
        notifiers=notifiers,
        keepalive=keepalive,
        secrets=secrets,
    )
