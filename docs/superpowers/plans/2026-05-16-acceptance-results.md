# QuotaMonitor v0.1.0 Acceptance Results

Date: 2026-05-16
Branch: `main`

## Summary

Release tag was **not created** because several release-gate criteria require real Telegram credentials, real Cloudflare deployment, or macOS reboot validation that depend on user-supplied secrets.

## Automated Tests

- **PASS**: `.venv/bin/pytest -v`
- Result: `120 passed in 0.20s`
- Re-verified: `120 passed in 0.22s` (second agent, same session)
- Environment note: `python3 -m pytest -v` fails on this Mac because system Python 3.14 does not have pytest installed. This matches the handover note that pytest lives in `.venv/`.

## Acceptance Criteria

| Criterion | Result | Evidence / blocker |
|---|---:|---|
| Fresh macOS, no dotfiles -> `setup` -> first test notification within 5 min via Telegram | BLOCKED / NOT RUN | No `~/.quota-monitor/` exists — clean environment confirmed. `run_wizard(non_interactive=True, primary='macos_native')` runs start-to-finish in isolated HOME, writes config.toml and .env, exits 0. Real Telegram path blocked on missing `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`. Setup wizard test-send was fixed in `6741392`; `.env` reuse from existing credentials also works (test: `test_interactive_wizard_reuses_existing_telegram_env`). |
| Fresh macOS + CF picked -> wrangler deploy succeeds, webhook_url written | BLOCKED / NOT RUN | `wrangler whoami` succeeds: `frankdingv@gmail.com`, OAuth token with Workers+KV write. Wrangler v4 KV command fixed in `0ac2750`, deploy cwd fixed in `20b942d`. Real deploy blocked on Telegram bot/chat credentials for Worker secrets. |
| Inject 5-turn jsonl fixture -> `run --dry-run` reports "would alert at <reset_time>" | PASS | Temp HOME with 6 user-message jsonl entries: `[dry-run] would alert: source=claude reset_at=1778984440`. Re-verified in second agent session. |
| `run` twice in same window -> first sends, second is silent | PASS | Isolated HOME with 10 fixture entries and `macos_native` primary: first `run` exited 0 and wrote `alerted_for_reset=1778980825`; second identical command exited 0, produced no output, state unchanged. Re-verified in second agent session. |
| keepalive=true + idle 5h -> `claude -p <random phrase>` actually runs (verify log) | BLOCKED / NOT RUN | Current Claude activity is active (agent is running). `polling_tick()` correctly checks `is_idle(timestamps, now, idle_seconds)` and only fires when idle threshold met. Keepalive integration in `run_once()` was fixed in `2015ad6` with test `test_run_once_runs_polling_keepalive_when_enabled`. Cannot physically wait 5h idle in this session. |
| Delete a config field -> `run` exits non-zero with a clear message | PASS | Temp config missing `notifiers.primary` returned exit code 2 and printed `[error] notifiers.primary must not be empty`. Re-verified in second agent session. |
| Corrupt state.json -> `run` self-heals + emits warn log | PASS | Temp state with `{not json` printed `[warn] state file corrupted (...) resetting to defaults` and exited 0. Re-verified in second agent session. |
| LaunchAgent + reboot Mac -> cron triggers within 5 min | BLOCKED / NOT RUN | `generate_launch_agent_plist()` produces valid XML (verified via `xml.etree.ElementTree.fromstring()`). Plist includes `RunAtLoad=true`, `StartInterval=300`. Unit coverage exists for plist generation and launchctl command calls. Requires installing LaunchAgent and rebooting a macOS account to verify real cron trigger. |
| AI Agent prep prompt to Claude Code -> agent completes prep unaided | PARTIAL / BLOCKED | Previous agent run completed available prep checks unaided: Python `3.11.15`, `claude` `2.1.143`, Wrangler `4.92.0`, Cloudflare OAuth login all passed. Isolated HOME wizard smoke with `macos_native` and skipped scheduler returned 0. Blocked on missing Telegram credentials for the Telegram-specific prep path. README.zh-CN localized in `2559e6b`; setup `.env` reuse and actual test-send path fixed in `6741392`. |
| `notify-test` succeeds for each enabled backend | PARTIAL / BLOCKED | macOS native: `notify-test --backend macos_native` exited 0, printed `sent test via macos_native`. Re-verified in second agent session with isolated HOME. Telegram and Cloudflare relay remain blocked until real Telegram credentials and relay `webhook_url` exist. |
| phrase pool over 11 keepalives -> first 10 unique, 11th starts new round | PASS | Local probe via `pick_phrase()` with 10-item pool: indices `8,3,1,0,6,2,5,7,4,9` (10 unique), then reset to `(6,)` on 11th call. `first10_unique=True`, `eleventh_new_round=True`. Re-verified in second agent session. |
| README.md / README.zh-CN.md section parity (manual diff) | PASS | Heading parity: 14 H2 sections in both files. EN and ZH headings correspond 1:1. Cloudflare cron/cost notes present in both. Re-verified in second agent session. |

## Open Release Blockers

1. **Telegram credentials needed**: provide `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to validate setup Telegram test, `notify-test --backend telegram`, and Cloudflare relay deploy (Worker secrets).
2. **Cloudflare real deploy**: requires Telegram credentials + explicit user approval (creates KV namespace + Worker on real account).
3. **keepalive idle 5h**: requires waiting for or creating an actually idle Claude environment (5h no activity).
4. **LaunchAgent reboot**: requires installing LaunchAgent and rebooting macOS to verify cron trigger.

## Tag Decision

`v0.1.0` was **not tagged** in this run. All code fixes have been applied; remaining blockers are credential/physical-access dependencies.
