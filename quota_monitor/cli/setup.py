import sys
from pathlib import Path
from typing import Optional

from ..i18n import set_locale, t
from ._input import ask_choice, ask_string, ask_yes_no
from ._preflight import preflight_check


def _render_config(answers: dict) -> str:
    keepalive_enabled = "true" if answers.get("keepalive_enabled") else "false"
    keepalive_strategy = answers.get("keepalive_strategy", "polling")
    primary = answers.get("primary", "telegram")
    fallback = answers.get("fallback", "")
    cf_enabled = "true" if answers.get("cloudflare_enabled") else "false"
    cf_url = answers.get("cloudflare_webhook_url", "")
    return f"""\
locale = "{answers.get("locale", "en")}"
log_level = "info"

[probes.claude]
enabled = {"true" if answers.get("claude_enabled", True) else "false"}
threshold_turns = 5
window_hours = 5

[probes.codex]
enabled = {"true" if answers.get("codex_enabled", False) else "false"}
threshold_percent = 30

[notifiers]
primary = "{primary}"
fallback = "{fallback}"

[notifiers.telegram]

[notifiers.cloudflare_relay]
enabled = {cf_enabled}
webhook_url = "{cf_url}"

[keepalive]
enabled = {keepalive_enabled}
strategy = "{keepalive_strategy}"
model = "haiku"
phrase_pool = []
seamless_trigger_minutes = 30
seamless_buffer_seconds = 60
"""


def _render_env(answers: dict) -> str:
    return (
        f"TELEGRAM_BOT_TOKEN={answers.get('telegram_bot_token', '')}\n"
        f"TELEGRAM_CHAT_ID={answers.get('telegram_chat_id', '')}\n"
    )


def _collect_interactive_answers() -> dict:
    """Walk the user through the wizard steps and return an answers dict."""
    answers: dict = {}

    print("\n=== (1/7) Language ===")
    locale_idx = ask_choice("Select language:", ["English", "中文"], default=0)
    answers["locale"] = "en" if locale_idx == 0 else "zh"
    set_locale(answers["locale"])

    print("\n=== (2/7) Services to monitor ===")
    answers["claude_enabled"] = ask_yes_no("Monitor Claude?", default=True)
    answers["codex_enabled"] = ask_yes_no("Monitor Codex (requires ~/.codex/auth.json)?", default=False)

    print("\n=== (3/7) Notification ===")
    primary_idx = ask_choice(
        "Primary notifier:",
        ["telegram (direct)", "macos_native", "cloudflare_relay (advanced)"],
        default=0,
    )
    answers["primary"] = ["telegram", "macos_native", "cloudflare_relay"][primary_idx]
    fallback_idx = ask_choice(
        "Fallback when primary fails:",
        ["macos_native", "(none)"],
        default=0,
    )
    answers["fallback"] = ["macos_native", ""][fallback_idx]

    print("\n=== (4/7) Telegram credentials ===")
    if answers["primary"] == "telegram" or answers["primary"] == "cloudflare_relay":
        answers["telegram_bot_token"] = ask_string("Bot token", secret=True)
        answers["telegram_chat_id"] = ask_string("Chat ID")
        answers["skip_telegram_test"] = not ask_yes_no("Send a test message?", default=True)
    else:
        answers["telegram_bot_token"] = ""
        answers["telegram_chat_id"] = ""

    # === (5/7) Cloudflare relay deployment (only if user picked it) ===
    if answers["primary"] == "cloudflare_relay":
        print("\n=== (5/7) Cloudflare relay deployment ===")
        errors, _ = preflight_check(need_wrangler=True)
        if errors:
            print("[error] CF preflight failed:")
            for e in errors:
                print(f"  - {e}")
            print("Fix and re-run setup.")
            raise SystemExit(2)
        from ._wrangler import deploy_cf_relay
        relay_dir = Path(__file__).resolve().parent.parent.parent / "cloudflare-relay"
        url = deploy_cf_relay(
            relay_dir=relay_dir,
            telegram_bot_token=answers["telegram_bot_token"],
            telegram_chat_id=answers["telegram_chat_id"],
        )
        if url is None:
            print("[error] Cloudflare deploy failed. Re-run setup once you fix the issue.")
            raise SystemExit(3)
        answers["cloudflare_enabled"] = True
        answers["cloudflare_webhook_url"] = f"{url}/api/schedule"
        print(f"Deployed: {url}")

    print("\n=== (6/7) Keepalive ===")
    print(t("wizard.keepalive.warning"))
    answers["keepalive_enabled"] = ask_yes_no("Enable keepalive?", default=False)
    if answers["keepalive_enabled"]:
        idx = ask_choice("Strategy:", ["polling (default)", "seamless (advanced)"], default=0)
        answers["keepalive_strategy"] = "polling" if idx == 0 else "seamless"

    print("\n=== (7/7) Schedule install ===")
    sched_idx = ask_choice(
        "Install scheduler:",
        ["LaunchAgent (recommended)", "Print crontab line only", "Skip"],
        default=0,
    )
    answers["schedule"] = ["launchagent", "crontab", "skip"][sched_idx]
    return answers


def _print_crontab_line() -> None:
    py = sys.executable
    print(f"\nAdd to your crontab:\n  */5 * * * * {py} -m quota_monitor run >> ~/.quota-monitor/quota-monitor.log 2>&1\n")


def _install_launchagent(*, data_dir: Path) -> None:
    from ..platform.schedule import generate_launch_agent_plist, install_launch_agent
    from ..platform.paths import launch_agent_path
    label = "io.github.frank.quotamonitor"
    plist = generate_launch_agent_plist(
        label=label,
        program_arguments=[sys.executable, "-m", "quota_monitor", "run"],
        interval_seconds=300,
        stdout_log=data_dir / "quota-monitor.log",
        stderr_log=data_dir / "quota-monitor.err.log",
    )
    install_launch_agent(plist_path=launch_agent_path(label), plist_content=plist)


def run_wizard(
    *,
    answers: Optional[dict] = None,
    config_path: Path,
    env_path: Path,
    data_dir: Path,
    non_interactive: bool = False,
) -> int:
    print("\n╔══════════════════════════════════╗")
    print("║   QuotaMonitor Setup Wizard     ║")
    print("╚══════════════════════════════════╝\n")

    errors, warnings = preflight_check(need_wrangler=False)
    for w in warnings:
        print(f"[warn] {w}")
    if errors:
        print("\n[error] preflight checks failed:")
        for e in errors:
            print(f"  - {e}")
        print("\nFix prerequisites and re-run (see README §Setup with your AI Agent).")
        return 2

    if not non_interactive:
        answers = _collect_interactive_answers()
    if answers is None:
        print("[error] no answers provided", file=sys.stderr)
        return 2

    data_dir.mkdir(parents=True, exist_ok=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.parent.mkdir(parents=True, exist_ok=True)

    config_path.write_text(_render_config(answers))
    env_path.write_text(_render_env(answers))
    print(f"\nWrote {config_path}\nWrote {env_path}")

    schedule = answers.get("schedule", "skip")
    if schedule == "launchagent":
        _install_launchagent(data_dir=data_dir)
        print("LaunchAgent installed.")
    elif schedule == "crontab":
        _print_crontab_line()

    set_locale(answers.get("locale", "en"))
    print(t("wizard.complete"))
    return 0
