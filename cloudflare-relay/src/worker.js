// QuotaMonitor relay worker - uses CF Queues for precise delayed Telegram delivery.
// Secrets (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) come from `wrangler secret`.

function handleClaudeStatus(payload) {
  if (payload.incident) {
    const icon = payload.incident.status === "resolved" ? "✅" : "🚨";
    return [
      `${icon} *Claude incident update*`,
      "",
      `*Event*: ${payload.incident.name}`,
      `*Status*: ${payload.incident.status}`,
      `*Detail*: ${payload.incident.incident_updates?.[0]?.body || "n/a"}`,
      `*Link*: ${payload.page?.url || "https://status.claude.com"}/incidents/${payload.incident.id}`,
    ].join("\n");
  }
  if (payload.component_update) {
    return [
      "⚠️ *Claude component status change*",
      "",
      `*Component*: ${payload.component.name}`,
      `*New status*: ${payload.component_update.new_status || payload.component.status}`,
    ].join("\n");
  }
  return null;
}

async function sendTelegram(env, text) {
  const url = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`;
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text, parse_mode: "Markdown" }),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`Telegram ${resp.status}: ${body}`);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/schedule" && request.method === "POST") {
      const data = await request.json();
      const resetEpoch = data.reset_time_epoch || Math.floor(Date.now() / 1000);
      const delaySeconds = Math.max(0, resetEpoch - Math.floor(Date.now() / 1000));
      const scheduleId = data.schedule_id || null;

      // Tombstone: if the client supplied a schedule_id and we have a KV
      // binding, record (id -> latest reset_epoch) with a 6h TTL. The Queue
      // consumer will compare its own message's reset_epoch against this
      // value when delivering; mismatch == "this message was superseded by
      // a later schedule for the same logical alert", drop silently.
      // No KV binding => fall back to no-dedupe behaviour (older deployments).
      if (scheduleId && env.SCHEDULE_TOMBSTONE) {
        try {
          await env.SCHEDULE_TOMBSTONE.put(
            `latest:${scheduleId}`,
            String(resetEpoch),
            { expirationTtl: 6 * 3600 },
          );
        } catch (e) {
          console.log("KV write failed (continuing):", e.message);
        }
      }

      await env.ALERTS_QUEUE.send(
        {
          message: data.message || "Quota reset",
          schedule_id: scheduleId,
          reset_time_epoch: resetEpoch,
        },
        { delaySeconds },
      );
      return new Response(JSON.stringify({ scheduled: true, delay_seconds: delaySeconds }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (request.method !== "POST") {
      return new Response("QuotaMonitor relay is alive.", { status: 200 });
    }

    // Webhook relay (Claude status, etc.) — send immediately.
    let payload = {};
    try { payload = JSON.parse(await request.text()); }
    catch { return new Response("bad json", { status: 400 }); }

    const handlers = [handleClaudeStatus];
    let text = null;
    for (const h of handlers) { text = h(payload); if (text) break; }
    if (!text) {
      const safe = JSON.stringify(payload, null, 2).substring(0, 3000);
      text = `ℹ️ *Unhandled webhook*\n\n\`\`\`json\n${safe}\n\`\`\``;
    }

    try {
      await sendTelegram(env, text);
      return new Response("ok", { status: 200 });
    } catch (e) {
      return new Response(e.message, { status: 502 });
    }
  },

  async queue(batch, env) {
    for (const msg of batch.messages) {
      try {
        // Tombstone check: if this message carries a schedule_id, look up the
        // latest schedule the client made for that ID. If our message's
        // reset_time_epoch is older than the latest, this one was superseded
        // — silently ack and skip delivery so the user only gets the most
        // recent schedule's notification.
        const scheduleId = msg.body.schedule_id;
        const ourResetEpoch = msg.body.reset_time_epoch;
        let deliveryKey = null;
        if (scheduleId && ourResetEpoch && env.SCHEDULE_TOMBSTONE) {
          const latest = await env.SCHEDULE_TOMBSTONE.get(`latest:${scheduleId}`);
          if (latest && Number(latest) !== ourResetEpoch) {
            console.log(`Superseded: ${scheduleId} ours=${ourResetEpoch} latest=${latest}`);
            msg.ack();
            continue;
          }
          deliveryKey = `delivered:${scheduleId}:${ourResetEpoch}`;
          const delivered = await env.SCHEDULE_TOMBSTONE.get(deliveryKey);
          if (delivered) {
            console.log(`Duplicate delivery skipped: ${scheduleId} reset=${ourResetEpoch}`);
            msg.ack();
            continue;
          }
        }
        await sendTelegram(env, msg.body.message);
        if (deliveryKey) {
          try {
            await env.SCHEDULE_TOMBSTONE.put(
              deliveryKey,
              "1",
              { expirationTtl: 6 * 3600 },
            );
          } catch (e) {
            console.log("KV delivered marker write failed (continuing):", e.message);
          }
        }
        msg.ack();
      } catch (e) {
        console.log("Queue delivery failed, will retry:", e.message);
        msg.retry();
      }
    }
  },
};
