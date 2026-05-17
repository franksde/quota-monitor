import sys
import shutil
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config.loader import ConfigError, load_config
from ..core.calibration import load_calibration, record_sample, save_calibration
from ..core.dispatch import DispatchOutcome, dispatch_alert
from ..core.state import ClaudeState, CodexState, load_state, save_state
from ..core.window import AlertDecision, LatestWindow, decide_alerts, replay_windows
from ..i18n import set_locale, t
from ..notifiers import Alert, Notifier
from ..notifiers.cloudflare_relay import CloudflareRelayNotifier
from ..notifiers.macos_native import MacOSNativeNotifier
from ..notifiers.telegram import TelegramNotifier
from ..platform import paths as platform_paths
from ..probes._throttled_fetch import FetchHint
from ..probes.claude import scan_claude
from ..probes.codex import CodexAuthMissingError, scan_codex
from ..probes.precise import read_precise
from ..statusline.installer import ensure_wrapper_installed


def _build_notifier(name: str, cfg, secrets: dict[str, str]) -> Optional[Notifier]:
    if not name:
        return None
    if name == "telegram":
        return TelegramNotifier(
            bot_token=secrets.get("TELEGRAM_BOT_TOKEN", ""),
            chat_id=secrets.get("TELEGRAM_CHAT_ID", ""),
        )
    if name == "macos_native":
        return MacOSNativeNotifier()
    if name == "cloudflare_relay":
        return CloudflareRelayNotifier(webhook_url=cfg.notifiers.cloudflare_relay.webhook_url)
    print(f"[error] unknown notifier: {name}", file=sys.stderr)
    return None


def _alert_for(decision: AlertDecision, *, estimated: bool = False) -> Alert:
    label = "Claude" if decision.source == "claude" else "Codex"
    # Display in the user's local timezone, no tz suffix. Most users open
    # notifications on their own machine and just want to see "11:48", not
    # "10:48 UTC" — the conversion overhead is real for non-tech audiences.
    reset_human = datetime.fromtimestamp(decision.reset_at).strftime("%Y-%m-%d %H:%M:%S")
    body = t("alert.body.recovered", source=label, reset_at_human=reset_human)
    if estimated:
        body += t("alert.suffix.estimated")
    return Alert(
        title=t("alert.title.recovered", source=label),
        body=body,
        reset_at=decision.reset_at,
        source=decision.source,
    )


def _codex_fetch_hint(state: CodexState) -> Optional[FetchHint]:
    if state.last_fetch_at <= 0 or state.last_reset_at <= 0:
        return None
    return FetchHint(
        last_fetch_at=state.last_fetch_at,
        last_used_percent=state.last_used_percent,
        last_reset_at=state.last_reset_at,
    )


def run_once(
    *,
    config_path: Path,
    env_path: Path,
    state_path: Path,
    now: float,
    dry_run: bool,
) -> int:
    try:
        cfg = load_config(config_path, env_path)
    except ConfigError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2

    set_locale(cfg.locale)
    state = load_state(state_path)

    # Self-heal: external tools (cc-switch swaps a full settings.json snapshot
    # per provider) can drop or mangle our statusLine entry. If a backup
    # exists the user wanted wrapper installed; restore it silently.
    try:
        if ensure_wrapper_installed(
            settings_path=platform_paths.claude_settings_file(),
            backup_path=platform_paths.statusline_original(),
        ):
            print(t("log.statusline_healed"), file=sys.stderr)
    except Exception as e:
        print(t("log.statusline_heal_failed", error=e), file=sys.stderr)

    claude_result = None
    if cfg.probes.claude.enabled:
        try:
            claude_result = scan_claude(
                app_dir=platform_paths.claude_app_dir(),
                cli_dir=platform_paths.claude_cli_dir(),
                costs_file=platform_paths.claude_costs_file(),
                now=now,
                window_seconds=cfg.probes.claude.window_hours * 3600,
            )
        except Exception as e:
            print(t("log.probe_failed", source="claude", error=e), file=sys.stderr)

    codex_result = None
    if cfg.probes.codex.enabled:
        try:
            codex_result = scan_codex(
                auth_file=platform_paths.codex_auth_file(),
                now=now,
                hint=_codex_fetch_hint(state.codex),
                threshold_percent=cfg.probes.codex.threshold_percent,
                base_interval_seconds=300,
            )
        except CodexAuthMissingError as e:
            print(t("log.probe_failed", source="codex", error=e), file=sys.stderr)
        except Exception as e:
            print(t("log.probe_failed", source="codex", error=e), file=sys.stderr)

    if codex_result is not None and codex_result.extra.get("fetched") is True:
        state = replace(state, codex=replace(
            state.codex,
            last_fetch_at=int(now),
            last_used_percent=int(codex_result.extra.get("used_percent", 0) or 0),
            last_reset_at=int(codex_result.extra.get("reset_at", 0) or 0),
        ))

    precise = None
    if cfg.probes.claude.enabled:
        precise = read_precise(platform_paths.rate_limits_cache(), now=now)

    calibration_state = load_calibration(platform_paths.calibration_file())

    if precise is not None:
        claude_source_type = "precise"
        if precise.five_hour_pct >= cfg.probes.claude.precise_threshold_percent:
            claude_window = LatestWindow(
                start=precise.five_hour_resets_at - (cfg.probes.claude.window_hours * 3600),
                reset=precise.five_hour_resets_at,
                count=cfg.probes.claude.threshold_turns,
            )
        else:
            claude_window = None

        if claude_result is not None:
            computed = replay_windows(claude_result.timestamps, correction=0.0)
            if computed is not None and computed.reset > now:
                diff = abs(precise.five_hour_resets_at - computed.reset)
                if diff < 1800:
                    calibration_state = record_sample(
                        calibration_state,
                        precise_reset=precise.five_hour_resets_at,
                        computed_reset=computed.reset,
                        ts=now,
                    )
                    save_calibration(platform_paths.calibration_file(), calibration_state)
    else:
        # Full Replay: compute the latest Claude window from probe timestamps alone.
        # State never participates in window slicing — see core/window.py docstring.
        claude_window = (
            replay_windows(
                claude_result.timestamps,
                correction=calibration_state.current_correction_seconds,
            )
            if claude_result is not None
            else None
        )
        claude_source_type = "estimated" if claude_window is not None else None

    decisions = decide_alerts(
        state=state,
        claude_window=claude_window,
        codex=codex_result,
        now=now,
        claude_threshold=cfg.probes.claude.threshold_turns,
        codex_threshold_percent=cfg.probes.codex.threshold_percent,
    )

    if dry_run:
        for d in decisions:
            print(f"[dry-run] would alert: source={d.source} reset_at={d.reset_at}")
        return 0

    primary = _build_notifier(cfg.notifiers.primary, cfg, cfg.secrets)
    fallback = _build_notifier(cfg.notifiers.fallback, cfg, cfg.secrets)
    if primary is None:
        print("[error] primary notifier could not be constructed", file=sys.stderr)
        return 3

    new_state = state
    for d in decisions:
        alert = _alert_for(
            d,
            estimated=d.source == "claude" and claude_source_type == "estimated",
        )
        outcome = dispatch_alert(alert, primary=primary, fallback=fallback)
        if outcome in (DispatchOutcome.PRIMARY_SUCCESS, DispatchOutcome.FALLBACK_SUCCESS):
            if d.source == "claude":
                # 4h cooldown — slightly under the 5h window so a real next
                # reset can still fire. Cooldown anchored to wall-clock time
                # (not d.reset_at) because the algorithm's reset_at can drift
                # by hours under third-party routing; trusting it for
                # cooldown would re-open the spam window.
                new_state = replace(new_state, claude=ClaudeState(
                    alerted_for_reset=d.reset_at,
                    cooldown_until=int(now) + 4 * 3600,
                ))
            elif d.source == "codex":
                new_state = replace(new_state, codex=replace(
                    new_state.codex,
                    alerted_for_reset=d.reset_at,
                    cooldown_until=d.reset_at,
                ))

    if cfg.keepalive.enabled:
        timestamps = claude_result.timestamps if claude_result is not None else ()
        claude_cli = shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")
        shell = "/bin/zsh"
        idle_seconds = cfg.probes.claude.window_hours * 3600
        if cfg.keepalive.strategy == "seamless":
            from ..keepalive.seamless import seamless_tick
            _, new_state = seamless_tick(
                state=new_state,
                now=now,
                timestamps=timestamps,
                claude_cli=claude_cli,
                shell=shell,
                model=cfg.keepalive.model,
                phrase_pool=cfg.keepalive.phrase_pool,
                trigger_minutes=cfg.keepalive.seamless_trigger_minutes,
                buffer_seconds=cfg.keepalive.seamless_buffer_seconds,
            )

    save_state(state_path, new_state)
    return 0
