import sys
from pathlib import Path
from typing import Optional

from ..config.loader import ConfigError, load_config
from ..i18n import set_locale
from ..notifiers import Alert
from ..notifiers.cloudflare_relay import CloudflareRelayNotifier
from ..notifiers.macos_native import MacOSNativeNotifier
from ..notifiers.telegram import TelegramNotifier


def send_test(*, config_path: Path, env_path: Path, backend: Optional[str]) -> int:
    try:
        cfg = load_config(config_path, env_path)
    except ConfigError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2
    set_locale(cfg.locale)

    name = backend or cfg.notifiers.primary
    if name == "telegram":
        notifier = TelegramNotifier(
            bot_token=cfg.secrets.get("TELEGRAM_BOT_TOKEN", ""),
            chat_id=cfg.secrets.get("TELEGRAM_CHAT_ID", ""),
        )
    elif name == "macos_native":
        notifier = MacOSNativeNotifier()
    elif name == "cloudflare_relay":
        notifier = CloudflareRelayNotifier(webhook_url=cfg.notifiers.cloudflare_relay.webhook_url)
    else:
        print(f"[error] unknown backend: {name}", file=sys.stderr)
        return 3

    alert = Alert(
        title="QuotaMonitor test",
        body="If you see this, your notifier is wired correctly.",
        reset_at=0,
        source="test",
    )
    try:
        notifier.send(alert)
    except Exception as e:
        print(f"[error] send failed: {e}", file=sys.stderr)
        return 4
    print(f"sent test via {name}")
    return 0
