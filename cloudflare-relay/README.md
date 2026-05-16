# QuotaMonitor — Cloudflare relay

Deployable Worker that receives schedule POSTs from the local CLI and fires
Telegram messages on time. Workers Free covers 100k requests/day. Workers KV
Free covers 100k reads/day, plus 1,000 writes/day, 1,000 deletes/day, and
1,000 list requests/day.

## Deploy

The `quota-monitor setup` wizard handles this for you. To deploy manually:

```bash
npm install -g wrangler
wrangler login
wrangler kv namespace create ALERTS_KV     # copy the id into wrangler.toml
cp wrangler.toml.example wrangler.toml      # paste the kv id
wrangler secret put TELEGRAM_BOT_TOKEN
wrangler secret put TELEGRAM_CHAT_ID
wrangler deploy
```

The default cron is every 3 minutes (`*/3 * * * *`), or 480 scheduled checks/day.
That stays below 500/day, the 50% point for the 1,000/day KV list quota. A
2-minute cron (`*/2 * * * *`) is possible, but may trigger daily usage-warning
emails.

The deployed URL goes into `~/.quota-monitor/config.toml`:

```toml
[notifiers.cloudflare_relay]
enabled = true
webhook_url = "https://<your-worker>.workers.dev/api/schedule"
```

## Security

Use a **scoped Cloudflare API token** (Workers + KV only) — never your
Global API Key. Revoke after deploy if you used an AI agent to assist.
