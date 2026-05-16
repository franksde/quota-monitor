// QuotaMonitor relay worker - schedules delayed Telegram alerts via KV.
// Secrets (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) come from `wrangler secret`,
// never hardcoded.

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
    console.log("Telegram error:", await resp.text());
    return new Response("telegram error", { status: 502 });
  }
  return new Response("ok", { status: 200 });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === "/api/schedule" && request.method === "POST") {
      try {
        const data = await request.json();
        const resetTime = data.reset_time_epoch || Math.floor(Date.now() / 1000);
        const key = `${resetTime}_${Math.random().toString(36).substring(2, 8)}`;
        await env.ALERTS_KV.put(key, JSON.stringify({ message: data.message || "Quota reset" }));
        return new Response("scheduled", { status: 200 });
      } catch (e) {
        return new Response(`schedule error: ${e.message}`, { status: 500 });
      }
    }

    if (request.method !== "POST") {
      return new Response("QuotaMonitor relay is alive.", { status: 200 });
    }

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
    return await sendTelegram(env, text);
  },

  async scheduled(event, env, ctx) {
    if (!env.ALERTS_KV) return;
    const now = Math.floor(Date.now() / 1000);
    const list = await env.ALERTS_KV.list();
    for (const key of list.keys) {
      const targetTime = parseInt(key.name.split("_")[0], 10);
      if (now < targetTime) continue;
      const raw = await env.ALERTS_KV.get(key.name);
      if (!raw) { await env.ALERTS_KV.delete(key.name); continue; }
      try {
        const data = JSON.parse(raw);
        const resp = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text: data.message, parse_mode: "Markdown" }),
        });
        if (resp.ok) await env.ALERTS_KV.delete(key.name);
        else console.log("scheduled telegram error:", await resp.text());
      } catch (e) {
        console.log("scheduled parse/network error:", e);
      }
    }
  },
};
