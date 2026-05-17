# QuotaMonitor — Cloudflare relay

Deployable Worker that receives schedule POSTs from the local CLI and fires
Telegram messages at the exact reset time using CF Queues delayed delivery.
Zero polling, zero KV operations.

## Deploy

The `quota-monitor setup` wizard handles this for you. To deploy manually:

```bash
npm install -g wrangler
wrangler login
cp wrangler.toml.example wrangler.toml
wrangler secret put TELEGRAM_BOT_TOKEN
wrangler secret put TELEGRAM_CHAT_ID
wrangler deploy
```

The Queue (`quota-monitor-alerts`) is created automatically on first deploy.

The deployed URL goes into `~/.quota-monitor/config.toml`:

```toml
[notifiers.cloudflare_relay]
enabled = true
webhook_url = "https://<your-worker>.workers.dev/api/schedule"
```

## Architecture

1. Local CLI POSTs `{reset_time_epoch, message}` to `/api/schedule`
2. Worker pushes message to Queue with `delaySeconds = reset_time - now`
3. Queue delivers message at the exact time; consumer sends to Telegram
4. Built-in retry (max 3) handles transient Telegram failures

## Security

Use a **scoped Cloudflare API token** (Workers + Queues only) — never your
Global API Key. Revoke after deploy if you used an AI agent to assist.
