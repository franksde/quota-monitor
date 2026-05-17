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

      await env.ALERTS_QUEUE.send(
        { message: data.message || "Quota reset" },
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
        await sendTelegram(env, msg.body.message);
        msg.ack();
      } catch (e) {
        console.log("Queue delivery failed, will retry:", e.message);
        msg.retry();
      }
    }
  },
};
