from unittest.mock import patch, MagicMock
from quota_monitor.cli._wrangler import deploy_cf_relay, prepare_cf_relay_workdir


def _ok(stdout=""):
    return MagicMock(returncode=0, stdout=stdout, stderr="")


def test_prepare_cf_relay_workdir_copies_bundled_worker_files(tmp_path):
    relay_dir = prepare_cf_relay_workdir(tmp_path / "relay-workdir")

    assert (relay_dir / "wrangler.toml.example").exists()
    assert (relay_dir / "package.json").exists()
    assert (relay_dir / "src" / "worker.js").exists()
    assert "SCHEDULE_TOMBSTONE" in (relay_dir / "wrangler.toml.example").read_text()
    assert "ALERTS_QUEUE" in (relay_dir / "src" / "worker.js").read_text()


def test_deploy_pushes_secrets_and_deploys(tmp_path):
    relay_dir = tmp_path / "cloudflare-relay"
    relay_dir.mkdir()
    (relay_dir / "wrangler.toml.example").write_text(
        'name = "qm-relay"\nmain = "src/worker.js"\n\n[[queues.producers]]\nqueue = "quota-monitor-alerts"\nbinding = "ALERTS_QUEUE"\n'
    )
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[:2] == ["wrangler", "worker"] and "list" in cmd:
            return _ok(stdout='[]\n')
        if cmd[:2] == ["wrangler", "deploy"]:
            return _ok(stdout='Published https://qm-relay-frank.workers.dev\n')
        return _ok()

    with patch("quota_monitor.cli._wrangler.subprocess.run", side_effect=fake_run):
        url = deploy_cf_relay(
            relay_dir=relay_dir,
            telegram_bot_token="TOK", telegram_chat_id="CID",
        )
    assert url == "https://qm-relay-frank.workers.dev"
    toml = (relay_dir / "wrangler.toml").read_text()
    assert "ALERTS_QUEUE" in toml
    secret_cmds = [c for c in calls if c[:3] == ["wrangler", "secret", "put"]]
    assert any("TELEGRAM_BOT_TOKEN" in c for c in secret_cmds)
    assert any("TELEGRAM_CHAT_ID" in c for c in secret_cmds)


def test_deploy_returns_none_on_wrangler_failure(tmp_path):
    relay_dir = tmp_path / "cloudflare-relay"
    relay_dir.mkdir()
    (relay_dir / "wrangler.toml.example").write_text('name = "qm-relay"\n')

    def fake_run(cmd, **kw):
        if cmd[:2] == ["wrangler", "worker"] and "list" in cmd:
            return _ok(stdout='[]\n')
        return MagicMock(returncode=1, stdout="", stderr="boom")

    with patch("quota_monitor.cli._wrangler.subprocess.run", side_effect=fake_run):
        url = deploy_cf_relay(
            relay_dir=relay_dir,
            telegram_bot_token="TOK", telegram_chat_id="CID",
        )
    assert url is None
