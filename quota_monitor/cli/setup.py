import json
import sys
from pathlib import Path
from typing import Optional

from ..config.dotenv import parse_dotenv
from ..i18n import set_locale, t
from ..statusline.installer import detect_existing_statusline, install_wrapper, StatusLineState
from .notify_test import send_test
from ._input import ask_choice, ask_string, ask_yes_no
from ._preflight import preflight_check


def _render_config(answers: dict) -> str:
    keepalive_enabled = "true" if answers.get("keepalive_enabled") else "false"
    keepalive_strategy = answers.get("keepalive_strategy", "seamless")
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
precise_threshold_percent = {int(answers.get("claude_precise_threshold_percent", 30))}

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


def _statusline_wizard_step(*, settings_path: Path, backup_path: Path) -> bool:
    state = detect_existing_statusline(settings_path)

    if state == StatusLineState.OUR_WRAPPER:
        print(t("wizard.statusline.already_configured"))
        return True

    if state == StatusLineState.NONE:
        prompt = t("wizard.statusline.enable_fresh")
    else:
        try:
            settings = json.loads(settings_path.read_text())
            statusline = settings.get("statusLine", "")
            if isinstance(statusline, dict):
                cmd_preview = (statusline.get("command") or "")[:30]
            else:
                cmd_preview = str(statusline)[:30]
        except (json.JSONDecodeError, OSError):
            cmd_preview = "unknown"
        prompt = t("wizard.statusline.enable_existing", cmd_preview=cmd_preview)

    if ask_yes_no(prompt, default=True):
        install_wrapper(settings_path=settings_path, backup_path=backup_path)
        print(t("wizard.statusline.installed"))
        return True
    return False


def _ask_percent(prompt: str, *, default: int = 30) -> int:
    while True:
        raw = ask_string(f"{prompt} [{default}]")
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            print("please enter a number between 0 and 100")
            continue
        if 0 <= value <= 100:
            return value
        print("please enter a number between 0 and 100")


def _collect_interactive_answers(*, existing_secrets: Optional[dict[str, str]] = None) -> dict:
    """Walk the user through the wizard steps and return an answers dict."""
    answers: dict = {}
    existing_secrets = existing_secrets or {}

    print("\n=== (1/8) Language ===")
    locale_idx = ask_choice("Select language:", ["English", "中文"], default=0)
    answers["locale"] = "en" if locale_idx == 0 else "zh"
    set_locale(answers["locale"])

    print(t("wizard.step2.title"))
    answers["claude_enabled"] = ask_yes_no(t("wizard.step2.claude"), default=True)
    answers["codex_enabled"] = ask_yes_no(t("wizard.step2.codex"), default=False)

    print(t("wizard.step3.title"))
    primary_idx = ask_choice(
        t("wizard.step3.primary"),
        t("wizard.step3.primary.options"),
        default=0,
    )
    answers["primary"] = ["telegram", "macos_native", "cloudflare_relay"][primary_idx]
    fallback_idx = ask_choice(
        t("wizard.step3.fallback"),
        t("wizard.step3.fallback.options"),
        default=0,
    )
    answers["fallback"] = ["macos_native", ""][fallback_idx]

    print(t("wizard.step4.title"))
    if answers["primary"] == "telegram" or answers["primary"] == "cloudflare_relay":
        existing_token = existing_secrets.get("TELEGRAM_BOT_TOKEN", "")
        existing_chat = existing_secrets.get("TELEGRAM_CHAT_ID", "")
        if existing_token and existing_chat:
            print(t("wizard.step4.use_existing"))
            answers["telegram_bot_token"] = existing_token
            answers["telegram_chat_id"] = existing_chat
        else:
            answers["telegram_bot_token"] = ask_string(t("wizard.step4.token"), secret=True)
            answers["telegram_chat_id"] = ask_string(t("wizard.step4.chat_id"))
        answers["skip_telegram_test"] = not ask_yes_no(t("wizard.step4.test"), default=True)
    else:
        answers["telegram_bot_token"] = ""
        answers["telegram_chat_id"] = ""

    # === (5/7) Cloudflare relay deployment (only if user picked it) ===
    if answers["primary"] == "cloudflare_relay":
        print(t("wizard.step5.title"))
        errors, _ = preflight_check(need_wrangler=True)
        if errors:
            print(t("wizard.step5.preflight_fail"))
            for e in errors:
                print(f"  - {e}")
            print(t("wizard.step5.fix_rerun"))
            raise SystemExit(2)
        from ._wrangler import deploy_cf_relay
        relay_dir = Path(__file__).resolve().parent.parent.parent / "cloudflare-relay"
        url = deploy_cf_relay(
            relay_dir=relay_dir,
            telegram_bot_token=answers["telegram_bot_token"],
            telegram_chat_id=answers["telegram_chat_id"],
        )
        if url is None:
            print(t("wizard.step5.deploy_fail"))
            raise SystemExit(3)
        answers["cloudflare_enabled"] = True
        answers["cloudflare_webhook_url"] = f"{url}/api/schedule"
        print(t("wizard.step5.deployed", url=url))

    print(t("wizard.step6.title"))
    print(t("wizard.keepalive.warning"))
    answers["keepalive_enabled"] = ask_yes_no(t("wizard.step6.enable"), default=False)
    if answers["keepalive_enabled"]:
        answers["keepalive_strategy"] = "seamless"

    print(t("wizard.statusline.title", step="7/8"))
    from ..platform import paths as platform_paths
    statusline_enabled = _statusline_wizard_step(
        settings_path=platform_paths.claude_settings_file(),
        backup_path=platform_paths.statusline_original(),
    )
    if statusline_enabled:
        answers["claude_precise_threshold_percent"] = _ask_percent(
            t("wizard.statusline.precise_threshold"),
            default=30,
        )

    print(t("wizard.step7.title"))
    sched_idx = ask_choice(
        t("wizard.step7.install"),
        t("wizard.step7.install.options"),
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
        existing_secrets = {}
        if env_path.exists():
            existing_secrets = parse_dotenv(env_path.read_text())
        answers = _collect_interactive_answers(existing_secrets=existing_secrets)
    if answers is None:
        print("[error] no answers provided", file=sys.stderr)
        return 2

    data_dir.mkdir(parents=True, exist_ok=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.parent.mkdir(parents=True, exist_ok=True)

    config_path.write_text(_render_config(answers))
    env_path.write_text(_render_env(answers))
    print(f"\nWrote {config_path}\nWrote {env_path}")

    if not answers.get("skip_telegram_test", True) and answers.get("primary") in ("telegram", "cloudflare_relay"):
        rc = send_test(config_path=config_path, env_path=env_path, backend=answers["primary"])
        if rc != 0:
            return rc

    schedule = answers.get("schedule", "skip")
    if schedule == "launchagent":
        _install_launchagent(data_dir=data_dir)
        print("LaunchAgent installed.")
    elif schedule == "crontab":
        _print_crontab_line()

    set_locale(answers.get("locale", "en"))
    print(t("wizard.complete"))
    return 0
