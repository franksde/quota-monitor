from unittest.mock import patch, MagicMock
from quota_monitor.cli._wrangler import deploy_cf_relay


def _ok(stdout=""):
    return MagicMock(returncode=0, stdout=stdout, stderr="")


def test_deploy_creates_kv_pushes_secrets_and_deploys(tmp_path):
    relay_dir = tmp_path / "cloudflare-relay"
    relay_dir.mkdir()
    (relay_dir / "wrangler.toml.example").write_text(
        'name = "qm-relay"\nmain = "src/worker.js"\n[[kv_namespaces]]\nbinding = "ALERTS_KV"\nid = "REPLACE_ME"\n'
    )
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[:3] == ["wrangler", "kv:namespace", "create"]:
            return _ok(stdout='{"id": "abc-kv-id"}\n')
        if cmd[:2] == ["wrangler", "deploy"]:
            return _ok(stdout='Published https://qm-relay-frank.workers.dev\n')
        return _ok()

    with patch("quota_monitor.cli._wrangler.subprocess.run", side_effect=fake_run):
        url = deploy_cf_relay(
            relay_dir=relay_dir,
            telegram_bot_token="TOK", telegram_chat_id="CID",
        )
    assert url == "https://qm-relay-frank.workers.dev"
    # wrangler.toml should be written with the real KV id substituted in.
    toml = (relay_dir / "wrangler.toml").read_text()
    assert "abc-kv-id" in toml
    assert "REPLACE_ME" not in toml
    # Secrets were pushed.
    secret_cmds = [c for c in calls if c[:3] == ["wrangler", "secret", "put"]]
    assert any("TELEGRAM_BOT_TOKEN" in c for c in secret_cmds)
    assert any("TELEGRAM_CHAT_ID" in c for c in secret_cmds)


def test_deploy_returns_none_on_wrangler_failure(tmp_path):
    relay_dir = tmp_path / "cloudflare-relay"
    relay_dir.mkdir()
    (relay_dir / "wrangler.toml.example").write_text("[[kv_namespaces]]\nbinding=\"ALERTS_KV\"\nid=\"REPLACE_ME\"\n")
    fail = MagicMock(returncode=1, stdout="", stderr="boom")
    with patch("quota_monitor.cli._wrangler.subprocess.run", return_value=fail):
        url = deploy_cf_relay(
            relay_dir=relay_dir,
            telegram_bot_token="TOK", telegram_chat_id="CID",
        )
    assert url is None
