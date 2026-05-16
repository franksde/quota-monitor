# Cloudflare Relay

The Cloudflare relay lets QuotaMonitor schedule delayed Telegram delivery even if the local Mac is asleep later.

## Automatic Setup

Run:

```bash
python3.11 -m quota_monitor setup
```

Choose `cloudflare_relay` as the primary notifier. The wizard will:

1. Verify `wrangler` is available.
2. Verify `wrangler whoami` succeeds.
3. Create `ALERTS_KV`.
4. Write `cloudflare-relay/wrangler.toml` from the example file.
5. Push `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as Worker secrets.
6. Deploy the Worker.
7. Write the deployed `/api/schedule` URL into `~/.quota-monitor/config.toml`.

## Manual Setup

```bash
npm install -g wrangler
wrangler login
cd cloudflare-relay
wrangler kv:namespace create ALERTS_KV
cp wrangler.toml.example wrangler.toml
$EDITOR wrangler.toml
wrangler secret put TELEGRAM_BOT_TOKEN
wrangler secret put TELEGRAM_CHAT_ID
wrangler deploy
```

Then configure:

```toml
[notifiers]
primary = "cloudflare_relay"
fallback = "macos_native"

[notifiers.cloudflare_relay]
enabled = true
webhook_url = "https://<your-worker>.workers.dev/api/schedule"
```

## Secret Rotation

Rotate Telegram credentials in @BotFather, then update Worker secrets:

```bash
cd cloudflare-relay
wrangler secret put TELEGRAM_BOT_TOKEN
wrangler secret put TELEGRAM_CHAT_ID
wrangler deploy
```

If you used a Cloudflare API token with an AI agent, revoke it after deploy.

## Debugging

Use:

```bash
cd cloudflare-relay
wrangler tail
```

Useful checks:

- `GET /` should return `QuotaMonitor relay is alive.`
- `POST /api/schedule` should return `scheduled`.
- KV keys should disappear after the scheduled cron sends them successfully.
- Telegram API errors are logged by the Worker.

## Cost Math

For personal use, the free tier is enough. A cron every 3 minutes is 480 scheduled invocations/day. A handful of scheduled alert writes and deletes is far below 100k KV operations/day.

## Security

Use a scoped Cloudflare API token with Workers + KV only. Never use or paste a Global API Key into an AI agent session.
