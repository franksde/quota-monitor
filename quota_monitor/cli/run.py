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
from ..core.window import AlertDecision, LatestWindow, WINDOW_SECONDS, decide_alerts, replay_windows, window_from_known_reset
from ..i18n import set_locale, t
from ..notifiers import Alert, Notifier
from ..keepalive.activation import fire_activation
from ..keepalive.phrases import PhraseState
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


def _has_threshold_activity_for_reset(claude_result, *, reset_at: float, threshold_turns: int) -> bool:
    if claude_result is None or not claude_result.timestamps:
        return False
    start = reset_at - WINDOW_SECONDS
    count = sum(1 for ts in claude_result.timestamps if start <= ts < reset_at)
    return count >= threshold_turns


def _best_known_future_reset(
    precise,
    claude_state,
    claude_result,
    now: float,
    *,
    threshold_turns: int,
) -> Optional[float]:
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
        if _has_threshold_activity_for_reset(
            claude_result,
            reset_at=candidate,
            threshold_turns=threshold_turns,
        ):
            return candidate
        return None
    if claude_state.last_known_good_reset_at:
        candidate = claude_state.last_known_good_reset_at + WINDOW_SECONDS
        while candidate <= now:
            candidate += WINDOW_SECONDS
        if _has_threshold_activity_for_reset(
            claude_result,
            reset_at=candidate,
            threshold_turns=threshold_turns,
        ):
            return candidate
        return None
    if claude_result and claude_result.timestamps:
        w = replay_windows(claude_result.timestamps)
        if w and w.reset > now:
            return w.reset
    return None


def _logical_schedule_id(source: str, reset_at: float) -> str:
    return f"{source}-{int((int(reset_at) + WINDOW_SECONDS // 2) // WINDOW_SECONDS)}"


def _maybe_post_reset_activate(
    *,
    cfg,
    state,
    precise,
    claude_result,
    now: float,
    dry_run: bool,
):
    """Post-reset window anchoring. When a Claude 5h window has rolled over
    and no local JSONL activity exists in the new window yet, fire one
    minimal Claude call so the next tick has a real-activity anchor —
    instead of relying on "anchor + N*5h" mechanical math which causes
    phantom-recovery notifications when the anchor goes stale.

    Strikes-out after cfg.keepalive.max_activation_attempts so a broken
    setup (tmux missing, network down, claude auth expired) doesn't
    re-fire every tick forever. Once activity appears in the window —
    either from a successful fire, or because the user came back and used
    Claude — strike state clears.
    """
    if not cfg.keepalive.enabled:
        return state

    # Step 1: resolve anchor. precise (HUD-fresh) wins over state-cached.
    if precise is not None:
        anchor = precise.five_hour_resets_at
    elif state.claude.last_known_good_reset_at > 0:
        anchor = state.claude.last_known_good_reset_at
    else:
        return state

    # Step 2: anchor must be in the past for "post-reset" to be meaningful.
    # Anchor in future = current window still active = nothing to anchor.
    if anchor > now:
        return state

    # Step 3: walk forward to the most recent reset boundary.
    n_periods = int((now - anchor) // WINDOW_SECONDS)
    most_recent_reset = anchor + n_periods * WINDOW_SECONDS
    key = int(most_recent_reset)

    # Step 4: if any timestamp lies inside the new window, we're done —
    # the next downstream tick will use replay_windows on real activity.
    has_post_reset_activity = (
        claude_result is not None
        and any(ts >= most_recent_reset for ts in claude_result.timestamps)
    )
    if has_post_reset_activity:
        return _clear_keepalive_state(state)

    # Step 5: strike budget. Once exhausted for this reset, don't fire
    # again until either activity appears (Step 4) or we cross into the
    # next period (which resets the count via the key change in Step 7).
    max_attempts = getattr(cfg.keepalive, "max_activation_attempts", 3)
    if (
        state.claude.keepalive_attempted_for_reset == key
        and state.claude.keepalive_attempt_count >= max_attempts
    ):
        return state

    # Step 6: fire (or dry-run pretend-fire).
    if dry_run:
        print(f"[dry-run] would activate keepalive for reset={key}")
        return _bump_keepalive_state(state, key)

    claude_cli = shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")
    phrase_state = PhraseState(
        used_indices=state.keepalive.phrase_pool_used_indices,
        size_at_init=state.keepalive.phrase_pool_size_at_init,
    )
    ok, new_phrase_state = fire_activation(
        claude_cli=claude_cli,
        shell="/bin/zsh",
        model=cfg.keepalive.model,
        phrase_pool=cfg.keepalive.phrase_pool,
        phrase_state=phrase_state,
        delay_seconds=0,
    )

    new_state = _bump_keepalive_state(state, key)
    if ok:
        new_state = replace(new_state, keepalive=replace(
            new_state.keepalive,
            phrase_pool_used_indices=new_phrase_state.used_indices,
            phrase_pool_size_at_init=new_phrase_state.size_at_init,
        ))
    return new_state


def _clear_keepalive_state(state):
    if (
        state.claude.keepalive_attempted_for_reset == 0
        and state.claude.keepalive_attempt_count == 0
    ):
        return state
    return replace(state, claude=replace(
        state.claude,
        keepalive_attempted_for_reset=0,
        keepalive_attempt_count=0,
    ))


def _bump_keepalive_state(state, key: int):
    """Step 7: same-reset → count++, new reset → count=1."""
    if state.claude.keepalive_attempted_for_reset == key:
        new_count = state.claude.keepalive_attempt_count + 1
    else:
        new_count = 1
    return replace(state, claude=replace(
        state.claude,
        keepalive_attempted_for_reset=key,
        keepalive_attempt_count=new_count,
    ))


def _maybe_schedule_cf_recovered_alert(
    *, cfg, state, precise, claude_result, codex_result, now: float, primary,
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
    from dataclasses import replace
    from datetime import datetime

    new_state = state

    # --- CLAUDE ---
    claude_threshold_hit = (
        (precise is not None and precise.five_hour_pct >= cfg.probes.claude.precise_threshold_percent)
        or (claude_result is not None and len(claude_result.timestamps) >= cfg.probes.claude.threshold_turns)
    )
    if claude_threshold_hit:
        best_reset = _best_known_future_reset(
            precise,
            new_state.claude,
            claude_result,
            now,
            threshold_turns=cfg.probes.claude.threshold_turns,
        )
        if best_reset is not None and new_state.claude.scheduled_alert_reset_at != int(best_reset):
            if dry_run:
                print(f"[dry-run] would CF-schedule: source=claude reset_at={int(best_reset)}")
                new_state = replace(new_state, claude=replace(
                    new_state.claude,
                    scheduled_alert_reset_at=int(best_reset),
                ))
            else:
                reset_human = datetime.fromtimestamp(best_reset).strftime("%Y-%m-%d %H:%M:%S")
                schedule_id = _logical_schedule_id("claude", best_reset)
                alert = Alert(
                    title=t("alert.title.recovered", source="Claude"),
                    body=t("alert.body.recovered", source="Claude", reset_at_human=reset_human),
                    reset_at=int(best_reset),
                    source="claude",
                    schedule_id=schedule_id,
                )
                try:
                    if primary: primary.send(alert)
                    new_state = replace(new_state, claude=replace(
                        new_state.claude,
                        scheduled_alert_reset_at=int(best_reset),
                    ))
                except Exception as e:
                    print(f"[warn] CF schedule failed for Claude: {e}", file=sys.stderr)

    # --- CODEX ---
    if codex_result is not None:
        used_percent = int(codex_result.extra.get("used_percent", 0) or 0)
        reset_at = codex_result.extra.get("reset_at")
        
        if reset_at is not None and reset_at > now and used_percent >= cfg.probes.codex.threshold_percent:
            if new_state.codex.scheduled_alert_reset_at != int(reset_at):
                if dry_run:
                    print(f"[dry-run] would CF-schedule: source=codex reset_at={int(reset_at)}")
                    new_state = replace(new_state, codex=replace(
                        new_state.codex,
                        scheduled_alert_reset_at=int(reset_at),
                    ))
                else:
                    reset_human = datetime.fromtimestamp(reset_at).strftime("%Y-%m-%d %H:%M:%S")
                    schedule_id = _logical_schedule_id("codex", reset_at)
                    alert = Alert(
                        title=t("alert.title.recovered", source="Codex"),
                        body=t("alert.body.recovered", source="Codex", reset_at_human=reset_human),
                        reset_at=int(reset_at),
                        source="codex",
                        schedule_id=schedule_id,
                    )
                    try:
                        if primary: primary.send(alert)
                        new_state = replace(new_state, codex=replace(
                            new_state.codex,
                            scheduled_alert_reset_at=int(reset_at),
                        ))
                    except Exception as e:
                        print(f"[warn] CF schedule failed for Codex: {e}", file=sys.stderr)

    return new_state


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

    if (
        codex_result is not None
        and (
            codex_result.extra.get("fetched") is True
            or codex_result.extra.get("source") == "codex-auth"
        )
    ):
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

    # Post-reset window anchoring. Runs in every mode (CF or polling) when
    # keepalive is enabled. Must run BEFORE the CF schedule block: even
    # though the fire-and-forget activation doesn't materialise in
    # claude_result.timestamps within this tick, the *next* tick will see
    # the new JSONL entry and the CF schedule will derive its target from
    # that real activity rather than from "stale anchor + 5h".
    new_state = _maybe_post_reset_activate(
        cfg=cfg, state=new_state, precise=precise,
        claude_result=claude_result, now=now, dry_run=dry_run,
    )

    is_cf_mode = cfg.notifiers.primary == "cloudflare_relay"

    # CF Queue mode: schedule the "recovered" alert at threshold-detection
    # time (now) so the Worker can hold it via delaySeconds and deliver
    # exactly at reset_at — even if the LaunchAgent isn't running then,
    # the terminal is closed, or precise data has gone stale.
    if is_cf_mode:
        if dry_run:
            new_state = _maybe_schedule_cf_recovered_alert(
                cfg=cfg, state=new_state, precise=precise,
                claude_result=claude_result, codex_result=codex_result, now=now, primary=None, dry_run=True,
            )
        else:
            cf_primary = _build_notifier(cfg.notifiers.primary, cfg, cfg.secrets)
            if cf_primary is None:
                print("[error] primary notifier could not be constructed", file=sys.stderr)
                return 3
            new_state = _maybe_schedule_cf_recovered_alert(
                cfg=cfg, state=new_state, precise=precise,
                claude_result=claude_result, codex_result=codex_result, now=now, primary=cf_primary, dry_run=False,
            )

    # In CF Queue mode, recovery is already handled above by delayed
    # scheduling for both Claude and Codex. Skip polling alerts for both.
    alert_claude_window = None if is_cf_mode else claude_window
    alert_codex_result = None if is_cf_mode else codex_result

    # Polling mode (TG-direct, macOS native, etc.): fire at reset_at via
    # the at-reset-recovered model. No way to defer with these notifiers,
    # so we must catch the reset moment in a LaunchAgent tick.
    decisions = decide_alerts(
        state=new_state,  # Use new_state here to ensure we don't ignore updates
        claude_window=alert_claude_window,
        codex=alert_codex_result,
        now=now,
        claude_threshold=cfg.probes.claude.threshold_turns,
        codex_threshold_percent=cfg.probes.codex.threshold_percent,
    )

    if dry_run:
        for d in decisions:
            print(f"[dry-run] would alert: source={d.source} reset_at={d.reset_at}")
        return 0

    if decisions:
        primary = _build_notifier(cfg.notifiers.primary, cfg, cfg.secrets)
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

    save_state(state_path, new_state)
    return 0
