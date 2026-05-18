from datetime import datetime
from pathlib import Path

from ..config.loader import ConfigError, load_config
from ..core.state import default_state, load_state
from ..i18n import set_locale, t


def _human(epoch: int) -> str:
    if epoch == 0:
        return "never"
    # Local timezone, no tz suffix — matches the alert body format and avoids
    # asking the user to mentally convert UTC.
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")


def show_status(*, state_path: Path, config_path: Path) -> int:
    try:
        cfg = load_config(config_path, env_path=None)
        set_locale(cfg.locale)
    except ConfigError:
        pass  # status still works without config

    state = load_state(state_path)
    if state == default_state():
        print(t("cli.status.no_state"))
        return 0

    # state only stores last alerted reset; window itself is derived live via probes
    # if the user wants real-time window info, they should run `quota-monitor run --dry-run`.
    print(t("cli.status.window", source="claude",
            start="(derived live — run --dry-run)",
            reset=_human(state.claude.alerted_for_reset)))
    print(t("cli.status.window", source="codex",
            start="-",
            reset=_human(state.codex.alerted_for_reset)))
    if state.claude.keepalive_attempted_for_reset:
        print(
            f"keepalive post-reset activation: tried for "
            f"{_human(state.claude.keepalive_attempted_for_reset)} "
            f"(attempts={state.claude.keepalive_attempt_count})"
        )
    print(f"keepalive phrase pool used: {len(state.keepalive.phrase_pool_used_indices)} / {state.keepalive.phrase_pool_size_at_init}")
    return 0
