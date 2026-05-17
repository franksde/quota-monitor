# QuotaMonitor

> Monitor Claude / Codex 5-hour quota windows and notify on reset. Zero-dependency Python, optional Cloudflare relay.

## Setup with your AI Agent (recommended)

This tool assumes you have a local AI agent (Claude Code / Codex / 
Gemini CLI / OpenClaw / Hermes). The smoothest path is to let it 
prepare the outside world before you run the wizard.

### Step 1 — Paste this prompt to your AI agent:

> I want to install QuotaMonitor (https://github.com/<repo>) on macOS.
> Read its README and prepare ALL prerequisites so the setup wizard
> runs from start to finish without interruption:
>
> 1. **Python ≥ 3.11**.  If missing: `brew install python@3.12`
> 2. **`claude` CLI** in PATH (only if I plan to enable keepalive).
> 3. **Telegram bot**: create via @BotFather, get token + chat_id, 
>    write them to `~/.quota-monitor/.env` using `.env.example`.
> 4. **Cloudflare relay** (recommended if I'm a developer):
>    - `npm install -g wrangler`
>    - `wrangler login`  (opens browser; I'll authenticate)
>    - Confirm `wrangler whoami` returns my account.
>    - Keep the relay cron at `*/3 * * * *` unless I explicitly choose
>      a faster schedule.
> 5. **Read README §Risks** with me — decide if I enable keepalive.
> 6. **Decide** schedule install: LaunchAgent (default) or manual cron.
>
> When prerequisites are ready, tell me to run:
>     python3.11 -m quota_monitor setup

### Step 2 — Run the wizard
    python3.11 -m quota_monitor setup

### Security note
If you give your AI agent a Cloudflare API token, use a **scoped 
token** (Workers + KV only), not your Global API Key. Revoke after.

## StatusLine Precise Usage Tracking (Optional)

quota-monitor can read real-time quota data directly from Claude Code via its [statusLine](https://docs.anthropic.com/en/docs/claude-code/status-line) mechanism, giving you precise 5-hour and 7-day usage percentages and exact reset times.

### How it works

1. The setup wizard configures a lightweight Python wrapper as your Claude Code statusLine command
2. Each time Claude Code updates its status bar, the wrapper:
   - Extracts `rate_limits` from the JSON payload
   - Writes it to a local cache (`~/.quota-monitor/rate_limits_cache.json`)
   - Forwards everything to your original statusLine tool (if any)
   - Returns the original output unchanged
3. When quota-monitor runs its periodic scan, it checks the cache first:
   - **Cache valid** → uses precise values (exact percentage and reset time)
   - **Cache expired** → falls back to local file replay estimation

### Compatibility

The wrapper is designed to work alongside existing statusLine tools:
- **Open Island** — detected and wrapped automatically
- **Claude HUD** — detected and wrapped automatically
- **ccstatusline** — detected and wrapped automatically
- **Custom scripts** — any existing `statusLine` config is preserved

### Manual install/uninstall

```bash
# Install (also available via `quota-monitor setup`)
quota-monitor statusline install

# Uninstall (also part of `quota-monitor uninstall`)
quota-monitor statusline uninstall
```

### Precise vs Estimated notifications

- Precise (from statusLine): triggers when `five_hour.used_percentage` reaches `probes.claude.precise_threshold_percent` (default `30`), then uses the exact statusLine reset time: "Quota resets at 15:30"
- Estimated (from local logs): "Quota resets at 15:30 (estimated from local conversation logs)"

### When the estimated reset can be wrong

The estimated path infers the 5-hour window boundary from local `~/.claude/projects/**/*.jsonl` timestamps. That works when Claude Code is the only thing burning your Anthropic quota. It can drift if either is true:

- **You use a third-party model router (e.g. `cc switch`).** Those calls write local jsonl entries that look like API calls, but they never reach Anthropic and don't shift Anthropic's 5-hour window. Conversely, the call that actually *started* Anthropic's current window may never appear locally.
- **You also use claude.ai web chat.** Web messages count toward the same 5-hour quota but are not written to any local file.

In either case, the probe is guessing. Measured drift on a real cc-switch install: **roughly 60 minutes off when activity is continuous; up to ~4 hours off shortly after the actual server-side reset** (replay can't see the reset event, so it keeps extending an already-stale window). The fix is to keep statusLine installed: it caches the precise reset time from Claude Code's own rate-limit headers and the probe trusts that when available.

## Quickstart (manual)

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e .
mkdir -p ~/.quota-monitor
cp config.example.toml ~/.quota-monitor/config.toml
cp .env.example ~/.quota-monitor/.env
$EDITOR ~/.quota-monitor/.env
.venv/bin/python -m quota_monitor notify-test
.venv/bin/python -m quota_monitor run --dry-run
```

Install the LaunchAgent through `python3.11 -m quota_monitor setup`, or use the Linux systemd template in `docs/linux-systemd.md`.

## What it does

QuotaMonitor scans local Claude activity logs and Codex usage metadata, derives the current quota window, and sends a notification when a reset should be actionable. It keeps only small state markers such as "already alerted for this reset", never conversation content.

Codex usage fetches are self-throttling: request frequency adapts to distance from the alert threshold, backing off to 10-20 minutes when usage is low and reusing cached data after the threshold is reached until the current window resets.

Optional features:

- Telegram direct notifications.
- macOS native notification fallback.
- Cloudflare relay for delayed delivery when your laptop may be asleep.
- Claude keepalive strategies, disabled by default.

## How it works (in 30 seconds)

1. `load_config()` reads TOML + `.env`. Schema validation failure exits with a clear setup hint.
2. `load_state()` reads `~/.quota-monitor/state.json`. Corruption resets to defaults and logs a warning.
3. Enabled probes collect timestamps or usage metadata. A single probe failure logs a warning and the rest continue.
4. `core.window.replay_windows()` derives the latest 5-hour window from timestamps alone. State never participates in window slicing.
5. `decide_alerts()` emits alert decisions only for reset points that have not already been notified.
6. `dispatch_alert()` sends to the primary notifier with retries, then fallback. State is updated only after a notifier succeeds.
7. Optional keepalive logic runs when explicitly enabled.

## Safety & privacy

- Zero runtime dependencies: Python stdlib only.
- Local-first: config, secrets, and state live under `~/.quota-monitor/`.
- Secrets live in `.env` or Cloudflare Worker secrets; they should never be committed.
- Claude probe code reads metadata and timestamps from local files. It does not upload conversation content.
- Cloudflare relay is optional. If enabled, only scheduled alert payloads are sent to your Worker.

## Cost

- Local mode costs $0.
- Telegram Bot API is free for normal personal usage.
- Cloudflare relay uses Workers + Queues + a tiny KV. CF Queues free tier allows 1M operations/month; each alert consumes 3 ops (send + deliver + ack), so heavy use (10 alerts/day) is ~900 ops/month. Workers Free allows 100k requests/day. Workers KV is used only as a schedule tombstone (≤10 ops/day, no `list` operations) so all KV free-tier limits are effectively non-binding.
- The relay is event-driven via CF Queues `delaySeconds` — no cron, no polling. Old QuotaMonitor versions ran a 3-minute cron that called KV `list` and could trigger Cloudflare's "50% usage warning" email; that design has been replaced.

## Choose your notification channel

| Channel | Best for | Tradeoff |
|---|---|---|
| Telegram direct | Most users | Requires bot token + chat id |
| macOS native | Local fallback while you are at the Mac | Cannot notify while the machine is asleep |
| Cloudflare relay | Delayed reset notification even if laptop is off | Requires `wrangler`, Cloudflare account, Worker + Queue + (optional) KV |

Recommended default: Telegram direct with macOS native fallback. Use Cloudflare relay if you care about delayed delivery while the laptop is not running.

## Adding a channel we don't support

Give this prompt to your AI agent:

```text
Add a new QuotaMonitor notifier named <name>. Read docs/adding-notifier.md.
Implement a Notifier class with name and send(Alert) -> None, wire it into
cli/run.py and cli/notify_test.py, add setup wizard options if appropriate,
and add pytest contract coverage following the Telegram notifier tests.
```

## Advanced: Cloudflare relay

The wizard can deploy the relay automatically when you pick `cloudflare_relay`. Manual instructions live in `docs/cloudflare.md` and `cloudflare-relay/README.md`.

The relay exposes:

- `POST /api/schedule`: enqueue a Telegram message into CF Queues with `delaySeconds = reset_time_epoch - now`. Optionally accepts a `schedule_id` so a later schedule for the same id supersedes the earlier one (KV tombstone, see `cloudflare-relay/README.md` for details).
- CF Queue consumer: at the scheduled time, checks the tombstone (if KV is bound) and delivers to Telegram, or silently ack-drops if superseded.
- Generic webhook handling for Claude status-style payloads.

## ⚠️ Risks

### Keepalive (auto-renew Claude 5h window)
- **Default: off.**
- **ToS**: Anthropic's AUP discourages automated usage. Enable at 
  your own risk; at scale this may invite attention or risk your account.
- **Sleep limitation**: keepalive **stops working** while macOS sleeps 
  (lid closed / idle sleep). Both `polling` and `seamless` strategies 
  fail under sleep. The natural 5h reset will still happen — keepalive 
  cannot save it.
- **Workarounds**: desktop / always-on machine, `caffeinate -i`, or 
  accept the natural reset.

### Keepalive content randomization — what it does and doesn't
We randomize keepalive content from a 10-phrase pool so no single 
message appears more than once per 10 keepalives. This neutralizes 
content-keyword detection.

**It does NOT defeat pattern-based detection** — request timing, token 
volume, session shape, and model choice are stronger signals than content. 
Use keepalive understanding any automated keep-window-alive behavior is 
detectable in principle.

### Secret leak
- Never commit `.env`. Rotate Telegram tokens via @BotFather if leaked.

## Platform support

| Platform | Status |
|---|---|
| macOS | Supported target for v1 |
| Linux | Best-effort; use `docs/linux-systemd.md` |
| Windows | Not supported |

## Troubleshooting

- `config file not found`: run `python3.11 -m quota_monitor setup`.
- Telegram credentials missing: check `~/.quota-monitor/.env`.
- No notification on second run: expected when the same reset was already alerted.
- Corrupt state: QuotaMonitor self-heals to default state and logs a warning.
- LaunchAgent did not load: run `launchctl load -w ~/Library/LaunchAgents/io.github.frank.quotamonitor.plist` manually and inspect stderr.
- Cloudflare deploy failed: run `wrangler whoami`, `wrangler tail`, and see `docs/cloudflare.md`.

## Architecture

See `docs/ARCHITECTURE.md`.

Core rule: the quota window is derived by Full Replay from probe timestamps on every tick. `state.json` stores notification dedupe markers only; it does not store window start or reset values.

## License

MIT. See `LICENSE`.
