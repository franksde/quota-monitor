# QuotaMonitor v0.1.0 Acceptance Results

Date: 2026-05-16
Branch: `main`

## Summary

Release tag was **not created** because several release-gate criteria require a clean macOS user account, real Telegram delivery, real Cloudflare deployment, or reboot validation that were not available in this execution environment.

## Automated Tests

- **PASS**: `.venv/bin/pytest -v`
- Result: `117 passed in 0.20s`
- Environment note: `python3 -m pytest -v` fails on this Mac because system Python 3.14 does not have pytest installed. This matches the handover note that pytest lives in `.venv/`.

## Acceptance Criteria

| Criterion | Result | Evidence / blocker |
|---|---:|---|
| Fresh macOS, no dotfiles -> `setup` -> first test notification within 5 min via Telegram | BLOCKED / NOT RUN | Requires a clean macOS user account and real Telegram bot/chat credentials. |
| Fresh macOS + CF picked -> wrangler deploy succeeds, webhook_url written | BLOCKED / NOT RUN | Requires real Cloudflare login/account, Worker deploy, KV namespace creation, and networked `wrangler deploy`. |
| Inject 5-turn jsonl fixture -> `run --dry-run` reports "would alert at <reset_time>" | PASS | Temp `HOME` with 5 user-message jsonl entries produced `[dry-run] would alert: source=claude reset_at=1778985461`. |
| `run` twice in same window -> first sends, second is silent | BLOCKED / NOT RUN | Requires either real notifier delivery or an acceptance harness that executes `run` with a dummy notifier outside unit tests. Unit coverage exists in `tests/test_cli_run.py::test_run_once_does_not_realert_in_same_window`. |
| keepalive=true + idle 5h -> `claude -p <random phrase>` actually runs (verify log) | BLOCKED / NOT RUN | Requires real `claude` CLI execution and keepalive runtime logging. Unit coverage exists for phrase selection and subprocess command construction. |
| Delete a config field -> `run` exits non-zero with a clear message | PASS | Temp config missing `notifiers.primary` returned exit code `2` and printed `[error] notifiers.primary must not be empty`. |
| Corrupt state.json -> `run` self-heals + emits warn log | PASS | Temp state with invalid JSON printed `[warn] state file corrupted (...) resetting to defaults` and exited `0`. |
| LaunchAgent + reboot Mac -> cron triggers within 5 min | BLOCKED / NOT RUN | Requires installing LaunchAgent and rebooting a macOS account. Unit coverage exists for plist generation and launchctl command calls. |
| AI Agent prep prompt to Claude Code -> agent completes prep unaided | BLOCKED / NOT RUN | Requires a separate Claude Code run against the published README. |
| `notify-test` succeeds for each enabled backend | BLOCKED / NOT RUN | Requires real Telegram/macOS/Cloudflare notification paths. Unit coverage exists for dispatching selected backends. |
| phrase pool over 11 keepalives -> first 10 unique, 11th starts new round | PASS | Local probe produced `0,1,2,3,4,5,6,7,8,9,0`; `first10_unique=True`, `eleventh_new_round=True`. |
| README.md / README.zh-CN.md section parity (manual diff) | PASS | Heading parity check returned `parity=True`, `count=14 14`. |

## Open Release Blockers

1. Run acceptance on a clean macOS user account.
2. Validate real Telegram `notify-test`.
3. Validate real Cloudflare relay deploy and scheduled delivery.
4. Validate LaunchAgent after reboot.
5. Run README AI Agent prep prompt with a separate agent.

## Tag Decision

`v0.1.0` was **not tagged** in this run.
