# QuotaMonitor Architecture

## Module Boundaries

| Module | Responsibility | Public surface | Depends on |
|---|---|---|---|
| `probes/` | Extract activity timestamps or usage metadata; no decisions. Includes `claude.py` (jsonl scan), `codex.py` (ChatGPT usage API + adaptive throttle), `precise.py` (priority chain), `hud_adapters.py` (HUD cache readers), `_throttled_fetch.py` (reusable fetch-rate helpers) | `ProbeResult`, `PreciseUsage`, `HudUsageData`, `FetchHint` | `platform.paths`, stdlib |
| `core/window.py` | Full Replay window derivation and alert decisions | `replay_windows()`, `window_from_known_reset()`, `decide_alerts()`, `RESET_GRACE_SECONDS` | `core.state`, `probes` dataclasses |
| `core/state.py` | Atomic JSON state IO with backward-compatible field load | `load_state()`, `save_state()`, `ClaudeState`, `CodexState` | stdlib |
| `core/calibration.py` | Sample-based correction of estimated reset using precise reset | `record_sample()`, `compute_correction()` | stdlib |
| `notifiers/` | `Notifier` Protocol and implementations (telegram, macos_native, cloudflare_relay) | `Notifier.send(Alert)`, `Alert(schedule_id=...)` | stdlib HTTP/subprocess |
| `keepalive/` | Optional `seamless` keepalive (detached tmux session sleeps until window end, fires minimal `claude -p` to renew) | `seamless_tick()` | `core.window`, `platform.schedule` |
| `platform/` | macOS paths and LaunchAgent plist generation | `paths.*`, `schedule.*` | stdlib |
| `config/` | TOML + `.env` load and validation | `Config`, `load_config()` | `tomllib`, stdlib |
| `statusline/` | Wraps Claude Code statusLine to extract `rate_limits` from stdin and self-heal when external tools (cc-switch) overwrite settings.json | `run_wrapper()`, `ensure_wrapper_installed()` | stdlib |
| `i18n/` | English/Chinese message lookup | `set_locale()`, `t()` | message tables |
| `cli/` | Setup, run, status, notify-test, uninstall | argparse entrypoints | all modules |

## Directory Structure

```text
quota-monitor/
├── README.md
├── README.zh-CN.md
├── cloudflare-relay/
│   ├── README.md
│   ├── package.json
│   ├── wrangler.toml.example
│   └── src/worker.js          # /api/schedule + Queue consumer + KV tombstone
├── docs/
│   ├── ARCHITECTURE.md
│   ├── adding-notifier.md
│   ├── adding-hud-adapter.md  # how to read a new HUD tool's cache
│   ├── cloudflare.md
│   └── linux-systemd.md
├── quota_monitor/
│   ├── cli/                   # setup, run, status, notify-test, uninstall
│   ├── config/                # TOML + .env
│   ├── core/                  # window, state, calibration, dispatch
│   ├── i18n/                  # EN/ZH message tables
│   ├── keepalive/             # seamless strategy
│   ├── notifiers/             # telegram, macos_native, cloudflare_relay
│   ├── platform/              # paths, LaunchAgent plist
│   ├── probes/                # claude, codex, precise, hud_adapters, _throttled_fetch
│   └── statusline/            # wrapper that hooks Claude Code statusLine
└── tests/
```

## Data Flow

```text
launchd
  -> python -m quota_monitor run
  -> load_config(TOML + .env)
  -> load_state(~/.quota-monitor/state.json)
  -> ensure_wrapper_installed (self-heal if cc-switch overwrote statusLine)
  -> enabled probes:
       claude:  scan_claude(jsonl timestamps)
       codex:   scan_codex(throttled; skips API when above threshold + reset in future)
  -> read_precise() priority chain for Claude:
       1. own statusline-wrapper cache (rate_limits_cache.json)
       2. claude-hud cache
       3. oh-my-claude cache
       4. None -> fall back to replay_windows estimate
  -> Construct LatestWindow:
       precise pct >= threshold -> use precise reset
       else if estimated path -> replay_windows(timestamps) with calibration,
              anchored to last_known_good_reset_at when available
  -> Decide:
       primary == cloudflare_relay:
         "schedule-ahead" model. If threshold hit (precise pct OR jsonl turns),
         dispatch Alert(reset_at = best_known_future_reset, schedule_id = ...).
         CF Worker queues with delaySeconds; KV tombstone supersedes earlier
         schedules for the same logical id.
       else:
         "recovered" polling model. decide_alerts fires when
         0 <= now - reset <= RESET_GRACE_SECONDS (30 min) AND
         count >= threshold AND not in cooldown AND not already alerted.
         Cooldown anchored to reset_at + grace (NOT wall-clock 4h).
  -> dispatch_alert(primary, fallback) only when state changes
  -> save_state() only after notifier success
  -> optional keepalive seamless_tick (tmux + minimal --bare claude -p)
```

## Full Replay State Flow

The original state-feedback pattern stored window start/reset and used saved values to filter future scans. If the saved reset drifted into the future, every historical timestamp could be filtered out and alerts would silently stop.

QuotaMonitor makes that failure mode structurally impossible:

- `replay_windows(timestamps)` takes no state.
- `decide_alerts` reads state only for dedupe (`alerted_for_reset`, `cooldown_until`, `scheduled_alert_reset_at`).
- Status output labels window values as derived live.
- Keepalive seamless strategy computes active windows from timestamps on every tick.
- `last_known_good_reset_at` (populated only from precise/HUD sources, never from replay) acts as a stable anchor for replay so estimated boundaries don't drift far from official ones.

## Precise Data: Priority Chain & Freshness

`probes/precise.py::read_precise` chain:

```
own statusline-wrapper cache  ← Claude Code stdin updates this when API responses carry rate_limits
  ↓ stale / missing
claude-hud cache              ← claude-hud polls Anthropic /api/oauth/usage every 5 min
  ↓ stale / missing
oh-my-claude cache            ← omc polls the same endpoint with a different cache schema
  ↓ stale / missing
None → caller falls back to replay_windows estimate
```

Freshness rule across all sources: a cache entry is honoured as long as its `reset_at` is in the future OR within `RESET_GRACE_SECONDS = 30 min` in the past. The reset time is a hard fact and doesn't decay with cache age; usage pct may be a few points stale but that's tolerable (one-tick alert delay at worst). All HUD caches are passive (refresh only when Claude Code is open), so the grace covers the "user is idle around reset" case.

Adding a new HUD adapter: ~50 lines + tests, see `docs/adding-hud-adapter.md`.

## Alert Models

Two paths, gated by the primary notifier type:

### CF schedule-ahead (primary = `cloudflare_relay`)

Decision time and delivery time are decoupled:

1. Any LaunchAgent tick that sees threshold hit (precise pct OR jsonl turns ≥ threshold_turns) dispatches `Alert(reset_at = best_known_future_reset, schedule_id = f"claude-{int(best_reset // WINDOW_SECONDS)}")`.
2. CF Worker computes `delaySeconds = reset_at - now` and queues via CF Queues.
3. KV tombstone: `latest:{schedule_id}` stores the most recent `reset_time_epoch`. Queue consumer compares at delivery; mismatch (a later schedule supersedes) → silent ack-drop. Lets quota-monitor refine its prediction (estimated → precise) without spamming the user.
4. Survives the user closing the terminal, LaunchAgent missing ticks around reset, all caches going stale — the message is already in the Queue.

State dedupe: `scheduled_alert_reset_at` skips re-dispatching the same future reset on every tick.

### Polling at-reset (primary = telegram / macos_native)

No way to defer with these notifiers, so the LaunchAgent must catch the reset moment:

1. `decide_alerts` fires when `0 <= now - reset <= RESET_GRACE_SECONDS` AND `count >= threshold` AND `cooldown_until <= now` AND `alerted_for_reset != reset_at`.
2. After a successful dispatch, `cooldown_until = max(reset_at + grace, now + 1h)`. Anchoring to reset_at (NOT wall-clock 4h) ensures the cooldown naturally expires before the next window's reset 5h later, so the next genuine alert is not swallowed.

## Codex Probe: Adaptive Throttling

`scan_codex` uses `_throttled_fetch.should_skip_fetch` to decide whether to hit the ChatGPT usage API:

- Above threshold + reset still in future → skip (no point re-asking, decision already made).
- Below threshold: dynamic interval based on distance to threshold (`compute_dynamic_interval`):
  - distance ≥ 20 → 20 min
  - distance ≥ 10 → 10 min
  - distance < 10 → 5 min (LaunchAgent base)
- First fetch (no `FetchHint`) → always go.

The `FetchHint` dataclass + `should_skip_fetch` / `compute_dynamic_interval` helpers are deliberately generic so future API-backed probes (e.g. Anthropic OAuth usage) can reuse the same throttling pattern.

State carries `last_fetch_at` / `last_used_percent` / `last_reset_at` for `CodexState`; updated only after a successful fetch.

## Error Handling

- Probe failures log warnings and do not stop other probes.
- Config errors return non-zero with clear guidance to run setup.
- State corruption resets to defaults with a warning. Field-level backward-compat: unknown keys silently ignored; missing newer keys default to 0.
- Notifier failures retry, then fallback; state is not marked as alerted unless a send succeeds.
- LaunchAgent install failures print manual `launchctl` guidance.
- statusLine wrapper self-heal (`ensure_wrapper_installed`) silently restores the wrapper when external tools (cc-switch swap, etc.) overwrite settings.json.
- KV tombstone provisioning failure during CF setup is non-fatal — the relay degrades to no-dedupe behaviour.
