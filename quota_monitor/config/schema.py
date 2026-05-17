from dataclasses import dataclass, field


@dataclass(frozen=True)
class ClaudeProbeConfig:
    enabled: bool = True
    threshold_turns: int = 5
    window_hours: int = 5
    precise_threshold_percent: int = 30


@dataclass(frozen=True)
class CodexProbeConfig:
    enabled: bool = True
    threshold_percent: int = 30


@dataclass(frozen=True)
class ProbesConfig:
    claude: ClaudeProbeConfig = field(default_factory=ClaudeProbeConfig)
    codex: CodexProbeConfig = field(default_factory=CodexProbeConfig)


@dataclass(frozen=True)
class CloudflareRelayConfig:
    enabled: bool = False
    webhook_url: str = ""


@dataclass(frozen=True)
class NotifiersConfig:
    primary: str = "telegram"
    fallback: str = "macos_native"
    cloudflare_relay: CloudflareRelayConfig = field(default_factory=CloudflareRelayConfig)


@dataclass(frozen=True)
class KeepaliveConfig:
    enabled: bool = False
    strategy: str = "polling"  # "polling" | "seamless"
    model: str = "haiku"
    phrase_pool: tuple[str, ...] = ()
    seamless_trigger_minutes: int = 30
    seamless_buffer_seconds: int = 60


@dataclass(frozen=True)
class Config:
    locale: str = "en"
    log_level: str = "info"
    probes: ProbesConfig = field(default_factory=ProbesConfig)
    notifiers: NotifiersConfig = field(default_factory=NotifiersConfig)
    keepalive: KeepaliveConfig = field(default_factory=KeepaliveConfig)
    secrets: dict[str, str] = field(default_factory=dict)


VALID_STRATEGIES = ("polling", "seamless")
VALID_LOCALES = ("en", "zh")
