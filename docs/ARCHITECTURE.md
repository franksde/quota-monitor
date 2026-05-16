# QuotaMonitor Architecture

## Module Boundaries

| Module | Responsibility | Public surface | Depends on |
|---|---|---|---|
| `probes/` | Extract activity timestamps or usage metadata; no decisions | `ProbeResult` | `platform.paths`, stdlib |
| `core/window.py` | Full Replay window derivation and alert decisions | `replay_windows()`, `decide_alerts()` | `core.state`, `probes` dataclasses |
| `core/state.py` | Atomic JSON state IO and corruption self-heal | `load_state()`, `save_state()` | stdlib |
| `notifiers/` | `Notifier` Protocol and implementations | `Notifier.send(Alert)` | stdlib HTTP/subprocess |
| `keepalive/` | Optional keepalive strategies and phrase sampling | `polling_tick()`, `seamless_tick()` | `core.window`, `platform.schedule` |
| `platform/` | macOS paths and LaunchAgent integration | `paths.*`, `schedule.*` | stdlib |
| `config/` | TOML + `.env` load and validation | `Config`, `load_config()` | `tomllib`, stdlib |
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
│   └── src/worker.js
├── docs/
│   ├── ARCHITECTURE.md
│   ├── adding-notifier.md
│   ├── cloudflare.md
│   └── linux-systemd.md
├── quota_monitor/
│   ├── cli/
│   ├── config/
│   ├── core/
│   ├── i18n/
│   ├── keepalive/
│   ├── notifiers/
│   ├── platform/
│   └── probes/
└── tests/
```

## Data Flow

```text
launchd / cron
  -> python -m quota_monitor run
  -> load_config(TOML + .env)
  -> load_state(~/.quota-monitor/state.json)
  -> enabled probes collect timestamps/metadata
  -> replay_windows(timestamps)
  -> decide_alerts(state, latest windows, thresholds)
  -> dispatch_alert(primary, fallback)
  -> save_state() only after notifier success
  -> optional keepalive tick
```

## Full Replay State Flow

The original state-feedback pattern stored window start/reset and used saved values to filter future scans. If the saved reset drifted into the future, every historical timestamp could be filtered out and alerts would silently stop.

QuotaMonitor v1 makes that failure mode structurally impossible:

- `replay_windows(timestamps)` takes no state.
- State stores only dedupe markers such as `claude.alerted_for_reset`.
- Status output labels window values as derived live.
- Keepalive polling and seamless strategies compute active windows from timestamps on every tick.

## Error Handling

- Probe failures log warnings and do not stop other probes.
- Config errors return non-zero with clear guidance to run setup.
- State corruption resets to defaults with a warning.
- Notifier failures retry, then fallback; state is not marked as alerted unless a send succeeds.
- LaunchAgent install failures print manual `launchctl` guidance.
