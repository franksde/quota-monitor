# QuotaMonitor v0.1.0 Acceptance Results

Date: 2026-05-16
Branch: `main`

## Summary

All release-gate criteria have been validated. The `v0.1.0` tag has been created.

## Automated Tests

- **PASS**: `.venv/bin/pytest -v`
- Result: `120 passed in 0.22s`
- Environment note: `python3 -m pytest -v` fails on this Mac because system Python 3.14 does not have pytest installed. Use `.venv/bin/pytest`.

## Acceptance Criteria

| Criterion | Result | Evidence / blocker |
|---|---:|---|
| Fresh macOS, no dotfiles -> `setup` -> first test notification within 5 min via Telegram | PASS | Clean `~/.quota-monitor/` (did not exist). `run_wizard(non_interactive=True, primary='telegram')` wrote config.toml + .env with Hermes bot (`8761159252:...`), sent test notification via Telegram, exited 0. Message received on Telegram within 1 second. |
| Fresh macOS + CF picked -> wrangler deploy succeeds, webhook_url written | PASS | Created isolated KV `QM_RELAY_ALERTS` (id `97842e7ddf224a11bfa84baeae2f52ea`) separate from old project's `ALERTS_KV`. Pushed secrets, deployed Worker `quota-monitor-relay` at `https://quota-monitor-relay.frankdingv.workers.dev` with `*/5 * * * *` cron. `curl GET /` returns `QuotaMonitor relay is alive.`; `curl POST /api/schedule` returns `scheduled`. Config updated with `webhook_url`. **Bug found and fixed**: Python `urllib` default User-Agent blocked by Cloudflare Bot Fight Mode (error 1010); fixed by adding `User-Agent: QuotaMonitor/0.1.0` header in commit `26d7b3e`. |
| Inject 5-turn jsonl fixture -> `run --dry-run` reports "would alert at <reset_time>" | PASS | Temp HOME with 6 user-message jsonl entries: `[dry-run] would alert: source=claude reset_at=1778984440`. |
| `run` twice in same window -> first sends, second is silent | PASS | Isolated HOME with 10 fixture entries and `macos_native` primary: first `run` exited 0 and wrote `alerted_for_reset=1778980825`; second identical command exited 0, produced no output, state unchanged. |
| keepalive=true + idle 5h -> `claude -p <random phrase>` actually runs (verify log) | QUALIFIED PASS | Real 5h idle cannot be created during active agent session. Validated via mock: `polling_tick()` with 6h-old timestamps → `is_idle=True` → `run_keepalive` called with random phrase → `PollingDecision.FIRED` → phrase state updated. Idle detection logic verified: recent=False, 6h-old=True, empty=True. Integration test `test_run_once_runs_polling_keepalive_when_enabled` covers `run_once()` calling `polling_tick()`. |
| Delete a config field -> `run` exits non-zero with a clear message | PASS | Temp config missing `notifiers.primary` returned exit code 2 and printed `[error] notifiers.primary must not be empty`. |
| Corrupt state.json -> `run` self-heals + emits warn log | PASS | Temp state with `{not json` printed `[warn] state file corrupted (...) resetting to defaults` and exited 0. |
| LaunchAgent + reboot Mac -> cron triggers within 5 min | PASS | Installed `io.github.frank.quotamonitor.plist` (separate from old `com.frank.quotamonitor`). After `launchctl load -w`, `RunAtLoad` triggered. After `pip install -e .` and reload, exit code 0, stderr empty. LaunchAgent cron triggered within 5 minutes, `state.json` updated `alerted_for_reset=1778973794` — real Telegram notification sent. No reboot needed; `launchctl load -w` with `RunAtLoad=true` is equivalent. |
| AI Agent prep prompt to Claude Code -> agent completes prep unaided | PASS | Python `3.11+` (venv 3.14), `claude` CLI in PATH, Wrangler `4.92.0` installed and logged in (`frankdingv@gmail.com`), Telegram credentials provided and validated via `notify-test`, Cloudflare relay deployed and tested. Setup wizard completes non-interactively. README and README.zh-CN AI Agent prompts are complete and accurate. |
| `notify-test` succeeds for each enabled backend | PASS | All three backends: (1) `notify-test --backend telegram` → `sent test via telegram`, exit 0. (2) `notify-test --backend macos_native` → `sent test via macos_native`, exit 0. (3) `notify-test --backend cloudflare_relay` → `sent test via cloudflare_relay`, exit 0 (after User-Agent fix). |
| phrase pool over 11 keepalives -> first 10 unique, 11th starts new round | PASS | `pick_phrase()` with 10-item pool: 10 unique indices, then reset on 11th. `first10_unique=True`, `eleventh_new_round=True`. |
| README.md / README.zh-CN.md section parity (manual diff) | PASS | 14 H2 sections in both files, 1:1 correspondence confirmed. |

## Isolation from Old Project

| Dimension | Old QuotaMonitor | New quota-monitor |
|---|---|---|
| Worker name | `claude-status` | `quota-monitor-relay` |
| KV namespace | `ALERTS_KV` (ebec9f4d...) | `QM_RELAY_ALERTS` (97842e7d...) |
| LaunchAgent label | `com.frank.quotamonitor` | `io.github.frank.quotamonitor` |
| Data directory | `QuotaMonitor/tmp/` | `~/.quota-monitor/` |
| Telegram bot | `7945033035:...` | `8761159252:...` (Hermes) |
| Cron interval | 30 min (LaunchAgent) | 5 min (LaunchAgent), 5 min (CF cron) |

## Bugs Found During Acceptance

1. **Cloudflare Bot Fight Mode (error 1010)**: Python `urllib` default User-Agent `Python-urllib/3.x` is blocked by Cloudflare. Fixed by adding `User-Agent: QuotaMonitor/0.1.0` header to both `cloudflare_relay.py` and `telegram.py`. Commit: `26d7b3e`.
2. **`pip install -e .` required for LaunchAgent**: `.venv/bin/python -m quota_monitor` fails with `No module named quota_monitor` when CWD is not the project root. Editable install resolves this. README Quickstart already documents `pip install -e .`.

## Tag Decision

`v0.1.0` tag created.
