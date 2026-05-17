# QuotaMonitor — Cloudflare relay

Deployable Worker that receives schedule POSTs from the local CLI and fires
Telegram messages at the exact reset time using CF Queues delayed delivery.
Zero polling. Uses a tiny KV namespace as schedule tombstone (≤ ~10 ops/day,
no list operations) so refined schedules can supersede outdated queued ones.

## Deploy

The `quota-monitor setup` wizard handles this for you. To deploy manually:

```bash
npm install -g wrangler
wrangler login
cp wrangler.toml.example wrangler.toml

# Provision the schedule-tombstone KV namespace, then paste the printed id
# into wrangler.toml under [[kv_namespaces]] (binding = "SCHEDULE_TOMBSTONE").
wrangler kv namespace create SCHEDULE_TOMBSTONE

wrangler secret put TELEGRAM_BOT_TOKEN
wrangler secret put TELEGRAM_CHAT_ID
wrangler deploy
```

The Queue (`quota-monitor-alerts`) is created automatically on first deploy.
The KV namespace is optional: without it the relay still works, it just
can't dedupe superseded schedules (user may receive 2-3 notifications when
quota-monitor refines its reset prediction).

The deployed URL goes into `~/.quota-monitor/config.toml`:

```toml
[notifiers.cloudflare_relay]
enabled = true
webhook_url = "https://<your-worker>.workers.dev/api/schedule"
```

## Architecture

1. Local CLI POSTs `{reset_time_epoch, message, schedule_id?}` to `/api/schedule`
2. Worker writes `(latest:{schedule_id} → reset_time_epoch)` to KV with 6h TTL
3. Worker pushes message to Queue with `delaySeconds = reset_time - now`
4. Queue delivers message at the exact time; consumer checks KV: if the
   message's `reset_time_epoch` no longer matches the latest value for its
   `schedule_id`, ack-and-drop (superseded). Otherwise send to Telegram.
5. Built-in retry (max 3) handles transient Telegram failures

## Security

Use a **scoped Cloudflare API token** (Workers + Queues + Workers KV) — never
your Global API Key. Revoke after deploy if you used an AI agent to assist.
