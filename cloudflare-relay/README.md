# QuotaMonitor — Cloudflare relay

Deployable Worker that receives schedule POSTs from the local CLI and fires
Telegram messages on time. Free tier covers 100k req/day and 100k KV ops/day.

## Deploy

The `quota-monitor setup` wizard handles this for you. To deploy manually:

```bash
npm install -g wrangler
wrangler login
wrangler kv:namespace create ALERTS_KV     # copy the id into wrangler.toml
cp wrangler.toml.example wrangler.toml      # paste the kv id
wrangler secret put TELEGRAM_BOT_TOKEN
wrangler secret put TELEGRAM_CHAT_ID
wrangler deploy
```

The deployed URL goes into `~/.quota-monitor/config.toml`:

```toml
[notifiers.cloudflare_relay]
enabled = true
webhook_url = "https://<your-worker>.workers.dev/api/schedule"
```

## Security

Use a **scoped Cloudflare API token** (Workers + KV only) — never your
Global API Key. Revoke after deploy if you used an AI agent to assist.
