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
from ..core.window import AlertDecision, LatestWindow, decide_alerts, replay_windows, window_from_known_reset
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

KNOWN_RESET_GRACE_SECONDS = 30 * 60


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


def _best_known_future_reset(precise, claude_state, claude_result, now: float) -> Optional[float]:
    """Pick the moment to schedule a 'recovered' notification for. Always
    returns a value strictly in the future, or None if we have nothing.

    Priority:
      1. precise data, reset still in future
      2. precise data, reset just passed -> predict next as +5h (assumes
         continuous activity which is the only case where a 'recovered'
         alert is relevant)
      3. last_known_good anchor (from earlier precise) + 5h
      4. replay_windows estimate
    """
    from ..core.window import WINDOW_SECONDS, replay_windows
    if precise and precise.five_hour_resets_at > now:
        return precise.five_hour_resets_at
    if precise:
        candidate = precise.five_hour_resets_at + WINDOW_SECONDS
        while candidate <= now:
            candidate += WINDOW_SECONDS
        return candidate
    if claude_state.last_known_good_reset_at:
        candidate = claude_state.last_known_good_reset_at + WINDOW_SECONDS
        while candidate <= now:
            candidate += WINDOW_SECONDS
        return candidate
    if claude_result and claude_result.timestamps:
        w = replay_windows(claude_result.timestamps)
        if w and w.reset > now:
            return w.reset
    return None


def _maybe_schedule_cf_recovered_alert(
    *, cfg, state, precise, claude_result, now: float, primary,
    dry_run: bool,
):
    """CF Queue mode: schedule the 'recovered' notification at threshold-
    detection time (NOT at reset time). CF Worker holds it via delaySeconds
    and pushes when the window resets. Decouples our decision moment from
    the notification delivery moment — survives the user closing the
    terminal, the LaunchAgent missing ticks around reset, etc.

    Threshold: precise pct >= threshold OR jsonl turns >= threshold_turns.
    Either qualifies — per user requirement, "missing a notification is
    worse than sending one slightly off-target".

    Returns possibly-updated state.
    """
    threshold_hit = (
        (precise is not None and precise.five_hour_pct >= cfg.probes.claude.precise_threshold_percent)
        or (claude_result is not None and len(claude_result.timestamps) >= cfg.probes.claude.threshold_turns)
    )
    if not threshold_hit:
        return state

    best_reset = _best_known_future_reset(precise, state.claude, claude_result, now)
    if best_reset is None:
        return state

    if state.claude.scheduled_alert_reset_at == int(best_reset):
        return state  # already queued this reset

    if dry_run:
        print(f"[dry-run] would CF-schedule: source=claude reset_at={int(best_reset)}")
        return state

    reset_human = datetime.fromtimestamp(best_reset).strftime("%Y-%m-%d %H:%M:%S")
    # Stable id per 5h window bucket. If best_reset is later updated within
    # the same logical window (precise data refines an earlier estimate),
    # the worker's KV tombstone treats the newer schedule as authoritative
    # and drops the older queued delivery — the user only gets one
    # notification with the most recent reset time.
    from ..core.window import WINDOW_SECONDS
    schedule_id = f"claude-{int(best_reset // WINDOW_SECONDS)}"
    alert = Alert(
        title=t("alert.title.recovered", source="Claude"),
        body=t("alert.body.recovered", source="Claude", reset_at_human=reset_human),
        reset_at=int(best_reset),
        source="claude",
        schedule_id=schedule_id,
    )
    try:
        primary.send(alert)
    except Exception as e:
        print(f"[warn] CF schedule failed: {e}", file=sys.stderr)
        return state

    return replace(state, claude=replace(
        state.claude,
        scheduled_alert_reset_at=int(best_reset),
    ))


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
    new_state = state

    if precise is not None:
        claude_source_type = "precise"
        new_state = replace(new_state, claude=replace(
            new_state.claude,
            last_known_good_reset_at=precise.five_hour_resets_at,
        ))
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
        claude_window = None
        if claude_result is not None:
            known_reset = state.claude.last_known_good_reset_at
            if known_reset and now - KNOWN_RESET_GRACE_SECONDS <= known_reset <= now + (
                cfg.probes.claude.window_hours * 3600
            ):
                claude_window = window_from_known_reset(
                    claude_result.timestamps,
                    reset_at=known_reset,
                )
            if claude_window is None:
                claude_window = replay_windows(
                    claude_result.timestamps,
                    correction=calibration_state.current_correction_seconds,
                )
        claude_source_type = "estimated" if claude_window is not None else None

    is_cf_mode = cfg.notifiers.primary == "cloudflare_relay"

    # CF Queue mode: schedule the "recovered" alert at threshold-detection
    # time (now) so the Worker can hold it via delaySeconds and deliver
    # exactly at reset_at — even if the LaunchAgent isn't running then,
    # the terminal is closed, or precise data has gone stale.
    if is_cf_mode:
        if dry_run:
            new_state = _maybe_schedule_cf_recovered_alert(
                cfg=cfg, state=new_state, precise=precise,
                claude_result=claude_result, now=now, primary=None, dry_run=True,
            )
        else:
            cf_primary = _build_notifier(cfg.notifiers.primary, cfg, cfg.secrets)
            if cf_primary is None:
                print("[error] primary notifier could not be constructed", file=sys.stderr)
                return 3
            new_state = _maybe_schedule_cf_recovered_alert(
                cfg=cfg, state=new_state, precise=precise,
                claude_result=claude_result, now=now, primary=cf_primary, dry_run=False,
            )

    # In CF Queue mode Claude recovery is already handled above by delayed
    # scheduling. Keep the polling alert path alive for Codex only.
    alert_claude_window = None if is_cf_mode else claude_window

    # Polling mode (TG-direct, macOS native, etc.): fire at reset_at via
    # the at-reset-recovered model. No way to defer with these notifiers,
    # so we must catch the reset moment in a LaunchAgent tick.
    decisions = decide_alerts(
        state=state,
        claude_window=alert_claude_window,
        codex=codex_result,
        now=now,
        claude_threshold=cfg.probes.claude.threshold_turns,
        codex_threshold_percent=cfg.probes.codex.threshold_percent,
    )

    if dry_run:
        for d in decisions:
            print(f"[dry-run] would alert: source={d.source} reset_at={d.reset_at}")
        return 0

    polling_primary_name = "telegram" if is_cf_mode else cfg.notifiers.primary
    primary = _build_notifier(polling_primary_name, cfg, cfg.secrets)
    fallback = _build_notifier(cfg.notifiers.fallback, cfg, cfg.secrets)
    if primary is None:
        print("[error] primary notifier could not be constructed", file=sys.stderr)
        return 3

    for d in decisions:
        alert = _alert_for(
            d,
            estimated=d.source == "claude" and claude_source_type == "estimated",
        )
        outcome = dispatch_alert(alert, primary=primary, fallback=fallback)
        if outcome in (DispatchOutcome.PRIMARY_SUCCESS, DispatchOutcome.FALLBACK_SUCCESS):
            if d.source == "claude":
                # Cooldown anchored to reset_at + 30 min grace (= same window
                # decide_alerts honours), NOT wall-clock 4h. Wall-clock 4h can
                # straddle the next real reset and silently swallow the next
                # legitimate "recovered" alert (hit in the wild 2026-05-17:
                # 4h cooldown set at 20:08 ate the 21:10 reset notification).
                # Anchoring to reset_at means cooldown naturally expires
                # before the next window's reset (5h away). max(..., now+1h)
                # defends against algorithm reset_at drift on the estimated path.
                cooldown_target = max(d.reset_at + 30 * 60, int(now) + 3600)
                new_state = replace(new_state, claude=replace(
                    new_state.claude,
                    alerted_for_reset=d.reset_at,
                    cooldown_until=cooldown_target,
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
            # Pass the precise/HUD-sourced anchor so seamless picks the right
            # moment to fire — otherwise it falls back to replay_windows
            # estimate which can drift hours from reality.
            known_reset = new_state.claude.last_known_good_reset_at or None
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
                known_reset_at=known_reset,
            )

    save_state(state_path, new_state)
    return 0
