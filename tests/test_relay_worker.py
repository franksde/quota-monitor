from pathlib import Path
import subprocess


def test_worker_skips_duplicate_schedule_delivery(tmp_path):
    worker_src = Path("quota_monitor/cloudflare_relay/src/worker.js")
    worker_module = tmp_path / "worker.mjs"
    worker_module.write_text(worker_src.read_text())
    harness = tmp_path / "harness.mjs"
    harness.write_text(
        """
import worker from './worker.mjs';

const delivered = [];
globalThis.fetch = async (_url, options) => {
  delivered.push(JSON.parse(options.body).text);
  return { ok: true, text: async () => '' };
};

const kv = new Map();
const env = {
  TELEGRAM_BOT_TOKEN: 'token',
  TELEGRAM_CHAT_ID: 'chat',
  SCHEDULE_TOMBSTONE: {
    async get(key) { return kv.get(key) ?? null; },
    async put(key, value) { kv.set(key, value); },
  },
};

let acked = 0;
const message = {
  message: '*Codex*',
  schedule_id: 'codex-123',
  reset_time_epoch: 123,
};
await worker.queue({
  messages: [
    { body: message, ack() { acked += 1; }, retry() { throw new Error('retry'); } },
    { body: message, ack() { acked += 1; }, retry() { throw new Error('retry'); } },
  ],
}, env);

if (delivered.length !== 1) {
  throw new Error(`expected one Telegram delivery, got ${delivered.length}`);
}
if (acked !== 2) {
  throw new Error(`expected both queue messages acked, got ${acked}`);
}
""",
    )

    result = subprocess.run(
        ["node", str(harness)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
