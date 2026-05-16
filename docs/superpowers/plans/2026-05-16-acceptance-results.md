# QuotaMonitor v0.1.0 Acceptance Results

Date: 2026-05-16
Branch: `main`

## Summary

Release tag was **not created** because several release-gate criteria require a clean macOS user account, real Telegram delivery, real Cloudflare deployment, or reboot validation that were not available in this execution environment.

## Automated Tests

- **PASS**: `.venv/bin/pytest -v`
- Result: `120 passed in 0.20s`
- Environment note: `python3 -m pytest -v` fails on this Mac because system Python 3.14 does not have pytest installed. This matches the handover note that pytest lives in `.venv/`.

## Acceptance Criteria

| Criterion | Result | Evidence / blocker |
|---|---:|---|
| Fresh macOS, no dotfiles -> `setup` -> first test notification within 5 min via Telegram | BLOCKED / NOT RUN | Current user has no `/Users/frank/.quota-monitor`; real Telegram bot token/chat id are not present, so true Telegram delivery cannot run. During acceptance, setup was found to ask for a test notification but never send it; fixed in `6741392` with `tests/test_wizard_smoke.py::test_wizard_sends_requested_test_notification`. Same commit also reuses existing `.env` Telegram credentials so AI-agent prep can feed the wizard. |
| Fresh macOS + CF picked -> wrangler deploy succeeds, webhook_url written | BLOCKED / NOT RUN | `npm install -g wrangler` installed Wrangler `4.92.0`; `wrangler login` succeeded and `wrangler whoami` reports the `Frankdingv@gmail.com's Account` account. Real deploy still blocked on Telegram bot/chat credentials for Worker secrets. During acceptance, Wrangler v4 rejected old `kv:namespace`; fixed to `wrangler kv namespace create` in `0ac2750`. Earlier `20b942d` fixed deploy cwd so `wrangler.toml` is used from `cloudflare-relay/`. |
| Inject 5-turn jsonl fixture -> `run --dry-run` reports "would alert at <reset_time>" | PASS | Temp `HOME` with 5 user-message jsonl entries produced `[dry-run] would alert: source=claude reset_at=1778985461`. |
| `run` twice in same window -> first sends, second is silent | PASS | Isolated HOME `/private/tmp/qm-accept-run-twice-1778968678` with 6 Claude jsonl user-message fixture entries and primary `macos_native`: first `env HOME=... .venv/bin/python -m quota_monitor run` exited `0` and wrote `alerted_for_reset=1778986078`; second identical command exited `0`, produced no output, and left `alerted_for_reset=1778986078` unchanged. |
| keepalive=true + idle 5h -> `claude -p <random phrase>` actually runs (verify log) | BLOCKED / NOT RUN | Real precheck found current Claude activity is not idle: `count=29`, `latest_age_seconds=2837`, `latest_age_hours=0.79`. During investigation, `run_once()` was found not to call keepalive at all; fixed in commit `2015ad6` with test `tests/test_cli_run.py::test_run_once_runs_polling_keepalive_when_enabled`, but the real idle-5h gate still requires waiting for or creating an actually idle environment. |
| Delete a config field -> `run` exits non-zero with a clear message | PASS | Temp config missing `notifiers.primary` returned exit code `2` and printed `[error] notifiers.primary must not be empty`. |
| Corrupt state.json -> `run` self-heals + emits warn log | PASS | Temp state with invalid JSON printed `[warn] state file corrupted (...) resetting to defaults` and exited `0`. |
| LaunchAgent + reboot Mac -> cron triggers within 5 min | BLOCKED / NOT RUN | Requires installing LaunchAgent and rebooting a macOS account. Unit coverage exists for plist generation and launchctl command calls. |
| AI Agent prep prompt to Claude Code -> agent completes prep unaided | PARTIAL / BLOCKED | Separate agent run completed available prep checks unaided: Python `3.11.15`, `claude` `2.1.143`, Wrangler `4.92.0`, and Cloudflare OAuth login all passed; isolated HOME wizard smoke with `macos_native` and skipped scheduler returned `0`. It blocked on missing `/Users/frank/.quota-monitor/.env`, `TELEGRAM_BOT_TOKEN=unset`, `TELEGRAM_CHAT_ID=unset`, and noted Cloudflare deploy would mutate real account/resources. README.zh-CN was localized in `2559e6b`; setup `.env` reuse and actual test-send path were fixed in `6741392`. |
| `notify-test` succeeds for each enabled backend | PARTIAL / BLOCKED | Isolated macOS backend check passed: `env HOME=/private/tmp/qm-accept-run-twice-1778968678 .venv/bin/python -m quota_monitor notify-test --backend macos_native` exited `0` and printed `sent test via macos_native`. Telegram and Cloudflare relay remain blocked until real Telegram credentials and relay `webhook_url` exist. |
| phrase pool over 11 keepalives -> first 10 unique, 11th starts new round | PASS | Local probe produced `0,1,2,3,4,5,6,7,8,9,0`; `first10_unique=True`, `eleventh_new_round=True`. |
| README.md / README.zh-CN.md section parity (manual diff) | PASS | Heading parity check returned `count=14 14` for top-level sections. Chinese README headings and AI-agent prompt are now localized; English README has matching Cloudflare cron/cost notes. |

## Open Release Blockers

1. Run acceptance on a clean macOS user account.
2. Validate real Telegram `notify-test`.
3. Validate real Cloudflare relay deploy and scheduled delivery.
4. Validate LaunchAgent after reboot.
5. Provide real Telegram credentials so README AI Agent prep can complete the Telegram-specific path.

## Tag Decision

`v0.1.0` was **not tagged** in this run.
