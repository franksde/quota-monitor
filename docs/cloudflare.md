# Cloudflare Relay

The Cloudflare relay lets QuotaMonitor schedule delayed Telegram delivery even if the local Mac is asleep later. Uses CF Queues for precise, zero-polling delayed delivery.

## Automatic Setup

Run:

```bash
python3.11 -m quota_monitor setup
```

Choose `cloudflare_relay` as the primary notifier. The wizard will:

1. Verify `wrangler` is available.
2. Verify `wrangler whoami` succeeds.
3. Write `cloudflare-relay/wrangler.toml` from the example file.
4. Push `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as Worker secrets.
5. Deploy the Worker (Queue is created automatically).
6. Write the deployed `/api/schedule` URL into `~/.quota-monitor/config.toml`.

## Manual Setup

```bash
npm install -g wrangler
wrangler login
cd cloudflare-relay
cp wrangler.toml.example wrangler.toml
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
- `POST /api/schedule` should return `{"scheduled": true, "delay_seconds": N}`.
- Telegram API errors are logged by the Worker and trigger Queue retries (max 3).

## Cost

The relay uses CF Queues Free tier: 1 million operations/month. Each alert consumes 3 operations (send + deliver + ack). Even heavy usage (10 alerts/day) = 900 ops/month — negligible.

No KV, no cron polling, no daily limit concerns.

## Claude Status Notifications (bonus)

The relay Worker also handles [Claude Status](https://status.anthropic.com) webhooks. When Claude has an incident or component status change, the Worker forwards it to your Telegram — no extra code needed.

### How to subscribe

1. Open [status.anthropic.com](https://status.anthropic.com).
2. Click **Subscribe to Updates**.
3. Choose **Webhook**.
4. Enter your Worker root URL: `https://<your-worker>.workers.dev` (not `/api/schedule`).
5. Confirm the subscription.

This is a one-time setup. You will receive Telegram messages like:

```
🚨 Claude incident update

Event: API Degraded Performance
Status: investigating
Detail: We are investigating reports of...
Link: https://status.anthropic.com/incidents/abc123
```

### How it works

The Worker checks incoming POST payloads for Atlassian Statuspage fields (`incident`, `component_update`). Matching payloads are formatted and forwarded to Telegram. Unrecognized payloads are forwarded as raw JSON.

## Security

Use a scoped Cloudflare API token with Workers + Queues permissions. Never use or paste a Global API Key into an AI agent session.
